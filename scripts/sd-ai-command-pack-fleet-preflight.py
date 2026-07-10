#!/usr/bin/env python3
"""Preflight sd-ai-command-pack fleet refresh candidates."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FLEET_MANIFEST = ROOT / "docs/fleet/consumers.json"
DEFAULT_PACK_MANIFEST = ROOT / "manifest.json"
PROVENANCE_FILE = Path(".sd-ai-command-pack/provenance.json")


@dataclass(frozen=True)
class FleetConsumer:
    name: str
    github: str
    path_hint: str
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class FleetPreflightResult:
    consumer: FleetConsumer
    repo_path: Path
    status: str
    installed_version: str | None
    target_version: str
    detail: str


def load_json_object(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"error: {label} not found: {path}") from None
    except json.JSONDecodeError as error:
        raise SystemExit(f"error: {label} is not valid JSON: {error}") from None
    if not isinstance(payload, dict):
        raise SystemExit(f"error: {label} must be a JSON object: {path}")
    return payload


def pack_version(manifest_path: Path = DEFAULT_PACK_MANIFEST) -> str:
    manifest = load_json_object(manifest_path, "pack manifest")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(f"error: pack manifest version is missing: {manifest_path}")
    return version.strip()


def load_fleet_consumers(path: Path = DEFAULT_FLEET_MANIFEST) -> list[FleetConsumer]:
    manifest = load_json_object(path, "fleet manifest")
    consumers = manifest.get("consumers")
    if not isinstance(consumers, list):
        raise SystemExit(f"error: fleet manifest consumers must be an array: {path}")

    parsed: list[FleetConsumer] = []
    seen: set[str] = set()
    for index, item in enumerate(consumers):
        if not isinstance(item, dict):
            raise SystemExit(
                f"error: fleet manifest consumers[{index}] must be an object"
            )
        name = item.get("name")
        github = item.get("github")
        path_hint = item.get("pathHint")
        platforms = item.get("platforms")
        if not isinstance(name, str) or not name:
            raise SystemExit(f"error: fleet manifest consumers[{index}] has no name")
        if name in seen:
            raise SystemExit(f"error: duplicate fleet consumer name: {name}")
        seen.add(name)
        if not isinstance(github, str) or "/" not in github:
            raise SystemExit(
                f"error: fleet manifest consumer {name} has invalid github slug"
            )
        if not isinstance(path_hint, str) or not path_hint:
            raise SystemExit(
                f"error: fleet manifest consumer {name} has invalid pathHint"
            )
        if not isinstance(platforms, list) or not platforms:
            raise SystemExit(
                f"error: fleet manifest consumer {name} must list platforms"
            )
        platform_values: list[str] = []
        seen_platforms: set[str] = set()
        for platform in platforms:
            if not isinstance(platform, str) or not platform:
                raise SystemExit(
                    f"error: fleet manifest consumer {name} has invalid platform"
                )
            if platform in seen_platforms:
                raise SystemExit(
                    f"error: fleet manifest consumer {name} repeats platform "
                    f"{platform}"
                )
            seen_platforms.add(platform)
            platform_values.append(platform)
        parsed.append(
            FleetConsumer(
                name=name,
                github=github,
                path_hint=path_hint,
                platforms=tuple(sorted(platform_values)),
            )
        )
    return parsed


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
    target_version = args.target_version or pack_version(args.manifest)
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
                [
                    {
                        "name": result.consumer.name,
                        "github": result.consumer.github,
                        "path": str(result.repo_path),
                        "platforms": list(result.consumer.platforms),
                        "status": result.status,
                        "installedVersion": result.installed_version,
                        "targetVersion": result.target_version,
                        "detail": result.detail,
                    }
                    for result in results
                ],
                indent=2,
            )
        )
    else:
        print(f"sd-ai-command-pack fleet target: {target_version}")
        for result in results:
            installed = result.installed_version or "unknown"
            print(
                f"{result.status:19} {result.consumer.github} "
                f"(installed: {installed}; platforms: "
                f"{', '.join(result.consumer.platforms)})"
            )
            print(f"  {result.detail}")
            if result.status != "at-target" and result.repo_path.is_dir():
                print(f"  install: {install_command(result)}")
                print(f"  audit:   {audit_command(result)}")

    if args.fail_on_refresh_needed and any(
        result.status != "at-target" for result in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
