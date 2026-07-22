#!/usr/bin/env python3
"""Preflight sd-ai-command-pack fleet refresh candidates."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
RELEASE_SCRIPT_DIR = ROOT / ".github/scripts"
if str(RELEASE_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(RELEASE_SCRIPT_DIR))

import sd_ai_command_pack_fleet_lib as fleet_lib  # noqa: E402
from release_identity import (  # noqa: E402
    ReleaseIdentityError,
    verify_release_identity,
)

FleetConsumer = fleet_lib.FleetConsumer

DEFAULT_FLEET_MANIFEST = ROOT / "docs/fleet/consumers.json"
DEFAULT_PACK_MANIFEST = ROOT / "manifest.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "docs/fleet/candidate-validation.json"
PROVENANCE_FILE = Path(".sd-ai-command-pack/provenance.json")


@dataclass(frozen=True)
class FleetPreflightResult:
    consumer: FleetConsumer
    repo_path: Path
    status: str
    installed_version: str | None
    target_version: str
    detail: str


def pack_version(manifest_path: Path = DEFAULT_PACK_MANIFEST) -> str:
    try:
        return fleet_lib.pack_version(manifest_path)
    except fleet_lib.FleetConfigError as error:
        raise SystemExit(f"error: {error}") from None


def load_fleet_consumers(path: Path = DEFAULT_FLEET_MANIFEST) -> list[FleetConsumer]:
    try:
        return fleet_lib.load_fleet_consumers(path)
    except fleet_lib.FleetConfigError as error:
        raise SystemExit(f"error: {error}") from None


def read_installed_version(repo_path: Path) -> str | None:
    provenance = repo_path / PROVENANCE_FILE
    try:
        payload = json.loads(provenance.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return None
    version = payload.get("version") if isinstance(payload, dict) else None
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def consumer_repo_path(consumer: FleetConsumer) -> Path:
    return Path(consumer.path_hint).expanduser()


def preflight_consumer(
    consumer: FleetConsumer,
    *,
    target_version: str,
) -> FleetPreflightResult:
    repo_path = consumer_repo_path(consumer)
    if not repo_path.is_dir():
        return FleetPreflightResult(
            consumer=consumer,
            repo_path=repo_path,
            status="missing-local-clone",
            installed_version=None,
            target_version=target_version,
            detail="local checkout not found; clone or update pathHint before rollout",
        )

    installed_version = read_installed_version(repo_path)
    if installed_version == target_version:
        return FleetPreflightResult(
            consumer=consumer,
            repo_path=repo_path,
            status="at-target",
            installed_version=installed_version,
            target_version=target_version,
            detail="skip; already at target version",
        )
    if installed_version is None:
        detail = "refresh needed; provenance missing or unreadable"
    else:
        detail = f"refresh needed; installed {installed_version}"
    return FleetPreflightResult(
        consumer=consumer,
        repo_path=repo_path,
        status="refresh-needed",
        installed_version=installed_version,
        target_version=target_version,
        detail=detail,
    )


def audit_command(result: FleetPreflightResult) -> str:
    command = [
        "python3",
        "scripts/sd-ai-command-pack-install-audit.py",
        "--repo",
        str(result.repo_path),
    ]
    for platform in result.consumer.platforms:
        command.extend(["--expected-platform", platform])
    return " ".join(shlex.quote(part) for part in command)


def install_command(result: FleetPreflightResult) -> str:
    command = ["python3", "install.py", str(result.repo_path), "--force"]
    for platform in result.consumer.platforms:
        command.extend(["--platform", platform])
    return " ".join(shlex.quote(part) for part in command)


def prepare_commands(result: FleetPreflightResult) -> list[str]:
    repo = shlex.quote(str(result.repo_path))
    return [
        f"(cd {repo} && {shlex.join(command)})"
        for command in result.consumer.candidate_prepare
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check which fleet consumers need an sd-ai-command-pack refresh."
    )
    parser.add_argument(
        "--fleet",
        type=Path,
        default=DEFAULT_FLEET_MANIFEST,
        help="fleet manifest JSON; defaults to docs/fleet/consumers.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_PACK_MANIFEST,
        help="pack manifest JSON; defaults to manifest.json",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_CANDIDATE_LEDGER,
        help=(
            "full-fleet candidate ledger; defaults to "
            "docs/fleet/candidate-validation.json"
        ),
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="Git remote whose immutable release tag must match; defaults to origin",
    )
    parser.add_argument(
        "--target-version",
        help="override the target version; defaults to manifest.json version",
    )
    parser.add_argument(
        "--consumer",
        action="append",
        help="limit checks to this consumer name; repeat to select several",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of a text summary",
    )
    parser.add_argument(
        "--fail-on-refresh-needed",
        action="store_true",
        help="exit nonzero when any consumer needs refresh or has no local clone",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        release_identity = verify_release_identity(
            args.manifest.resolve().parent,
            manifest_path=args.manifest,
            fleet_path=args.fleet,
            ledger_path=args.ledger,
            remote=args.remote,
        )
    except ReleaseIdentityError as error:
        print(f"release identity error: {error}", file=sys.stderr)
        return 1

    target_version = release_identity.version
    if args.target_version and args.target_version != target_version:
        raise SystemExit(
            "error: --target-version must match the verified manifest release "
            f"{target_version}"
        )
    consumers = load_fleet_consumers(args.fleet)
    selected = set(args.consumer or [])
    if selected:
        known = {consumer.name for consumer in consumers}
        unknown = sorted(selected - known)
        if unknown:
            raise SystemExit(f"error: unknown fleet consumer(s): {', '.join(unknown)}")
        consumers = [consumer for consumer in consumers if consumer.name in selected]

    results = [
        preflight_consumer(consumer, target_version=target_version)
        for consumer in consumers
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "releaseIdentity": release_identity.as_json(),
                    "consumers": [
                        {
                            "name": result.consumer.name,
                            "github": result.consumer.github,
                            "path": str(result.repo_path),
                            "platforms": list(result.consumer.platforms),
                            "rolloutPriority": result.consumer.rollout_priority,
                            "candidatePrepare": [
                                list(command)
                                for command in result.consumer.candidate_prepare
                            ],
                            "candidateChecks": [
                                list(command)
                                for command in result.consumer.candidate_checks
                            ],
                            "status": result.status,
                            "installedVersion": result.installed_version,
                            "targetVersion": result.target_version,
                            "detail": result.detail,
                        }
                        for result in results
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            f"release identity: {release_identity.status} "
            f"{release_identity.tag} at {release_identity.commit_sha} "
            f"({release_identity.payload_digest})"
        )
        print(f"sd-ai-command-pack fleet target: {target_version}")
        for result in results:
            installed = result.installed_version or "unknown"
            print(
                f"{result.status:19} P{result.consumer.rollout_priority:02d} "
                f"{result.consumer.github} "
                f"(installed: {installed}; platforms: "
                f"{', '.join(result.consumer.platforms)})"
            )
            print(f"  {result.detail}")
            if result.status != "at-target" and result.repo_path.is_dir():
                print(f"  install: {install_command(result)}")
                print(f"  audit:   {audit_command(result)}")
                for index, command in enumerate(prepare_commands(result), start=1):
                    print(f"  prepare[{index}]: {command}")

    if args.fail_on_refresh_needed and any(
        result.status != "at-target" for result in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
