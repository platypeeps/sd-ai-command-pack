#!/usr/bin/env python3
"""Validate a pack release candidate against disposable fleet checkouts."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sd_ai_command_pack_fleet_lib import (  # noqa: E402
    CANDIDATE_LEDGER_SCHEMA_VERSION,
    FleetConfigError,
    FleetConsumer,
    filesystem_payload_digest,
    fleet_manifest_digest,
    load_fleet_consumers,
    load_json_object,
    manifest_version,
    validate_candidate_ledger,
)

DEFAULT_FLEET_MANIFEST = ROOT / "docs/fleet/consumers.json"
DEFAULT_PACK_MANIFEST = ROOT / "manifest.json"
DEFAULT_LEDGER = ROOT / "docs/fleet/candidate-validation.json"
INSTALL_AUDIT = ROOT / "scripts/sd-ai-command-pack-install-audit.py"
COMMAND_OUTPUT_LINES = 30
INFRASTRUCTURE_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str
    duration_seconds: float


@dataclass(frozen=True)
class CandidateResult:
    consumer: FleetConsumer
    status: str
    base_commit: str | None
    detail: str
    duration_seconds: float


def command_environment(python_executable: Path, work_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("COVERAGE_FILE", None)
    env.pop("COVERAGE_PROCESS_START", None)
    python_bin = str(python_executable.resolve().parent)
    inherited_path = env.get("PATH")
    env["PATH"] = (
        os.pathsep.join([python_bin, inherited_path]) if inherited_path else python_bin
    )
    env["PYTHONPYCACHEPREFIX"] = str(work_root / "python-cache")
    env["NPM_CONFIG_CACHE"] = str(work_root / "npm-cache")
    env["UV_CACHE_DIR"] = str(work_root / "uv-cache")
    env["SD_AI_COMMAND_PACK_CANDIDATE_CHECK"] = "1"
    return env


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str],
) -> CommandResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout_seconds,
        )
        return CommandResult(
            returncode=result.returncode,
            output=result.stdout,
            duration_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return CommandResult(
            returncode=124,
            output=f"{output}\ncommand timed out after {timeout_seconds}s".strip(),
            duration_seconds=time.monotonic() - started,
        )
    except (OSError, UnicodeError) as error:
        return CommandResult(
            returncode=127,
            output=f"command failed to start or decode output: {error}",
            duration_seconds=time.monotonic() - started,
        )


def concise_failure(label: str, command: Sequence[str], result: CommandResult) -> str:
    lines = [line for line in result.output.splitlines() if line.strip()]
    tail = "\n".join(lines[-COMMAND_OUTPUT_LINES:])
    detail = (
        f"{label} failed with exit {result.returncode}: {shlex.join(command)}"
    )
    return f"{detail}\n{tail}" if tail else detail


def validate_consumer(
    consumer: FleetConsumer,
    *,
    pack_root: Path,
    work_root: Path,
    python_executable: Path,
) -> CandidateResult:
    started = time.monotonic()
    source_checkout = Path(consumer.path_hint).expanduser()
    if not source_checkout.is_dir():
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=f"local checkout not found: {source_checkout}",
            duration_seconds=time.monotonic() - started,
        )

    env = command_environment(python_executable, work_root)
    origin_command = ["git", "-C", str(source_checkout), "remote", "get-url", "origin"]
    origin_result = run_command(
        origin_command,
        cwd=pack_root,
        timeout_seconds=60,
        env=env,
    )
    if origin_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=concise_failure("origin lookup", origin_command, origin_result),
            duration_seconds=time.monotonic() - started,
        )
    origin_url = origin_result.output.strip()
    if not origin_url:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail="origin lookup returned an empty URL",
            duration_seconds=time.monotonic() - started,
        )

    checkout = work_root / consumer.name
    clone_command = [
        "git",
        "clone",
        "--quiet",
        "--no-tags",
        "--single-branch",
        "--",
        origin_url,
        str(checkout),
    ]
    clone_result = run_command(
        clone_command,
        cwd=work_root,
        timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
        env=env,
    )
    if clone_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=concise_failure("clone", clone_command, clone_result),
            duration_seconds=time.monotonic() - started,
        )

    head_command = ["git", "rev-parse", "HEAD"]
    head_result = run_command(
        head_command,
        cwd=checkout,
        timeout_seconds=60,
        env=env,
    )
    base_commit = head_result.output.strip() if head_result.returncode == 0 else None
    if base_commit is None:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=None,
            detail=concise_failure("base commit lookup", head_command, head_result),
            duration_seconds=time.monotonic() - started,
        )

    install_command = [
        str(python_executable),
        str(pack_root / "install.py"),
        str(checkout),
        "--force",
    ]
    for platform in consumer.platforms:
        install_command.extend(["--platform", platform])
    install_result = run_command(
        install_command,
        cwd=pack_root,
        timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
        env=env,
    )
    if install_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail=concise_failure("install", install_command, install_result),
            duration_seconds=time.monotonic() - started,
        )

    audit_command = [
        str(python_executable),
        str(pack_root / "scripts/sd-ai-command-pack-install-audit.py"),
        "--repo",
        str(checkout),
    ]
    for platform in consumer.platforms:
        audit_command.extend(["--expected-platform", platform])
    audit_result = run_command(
        audit_command,
        cwd=pack_root,
        timeout_seconds=INFRASTRUCTURE_TIMEOUT_SECONDS,
        env=env,
    )
    if audit_result.returncode != 0:
        return CandidateResult(
            consumer=consumer,
            status="failed",
            base_commit=base_commit,
            detail=concise_failure("install audit", audit_command, audit_result),
            duration_seconds=time.monotonic() - started,
        )

    for prepare_index, command in enumerate(consumer.candidate_prepare, start=1):
        prepare_result = run_command(
            command,
            cwd=checkout,
            timeout_seconds=consumer.candidate_timeout_seconds,
            env=env,
        )
        if prepare_result.returncode != 0:
            return CandidateResult(
                consumer=consumer,
                status="failed",
                base_commit=base_commit,
                detail=concise_failure(
                    f"candidate preparation {prepare_index}",
                    command,
                    prepare_result,
                ),
                duration_seconds=time.monotonic() - started,
            )

    for check_index, command in enumerate(consumer.candidate_checks, start=1):
        check_result = run_command(
            command,
            cwd=checkout,
            timeout_seconds=consumer.candidate_timeout_seconds,
            env=env,
        )
        if check_result.returncode != 0:
            return CandidateResult(
                consumer=consumer,
                status="failed",
                base_commit=base_commit,
                detail=concise_failure(
                    f"candidate check {check_index}", command, check_result
                ),
                duration_seconds=time.monotonic() - started,
            )

    return CandidateResult(
        consumer=consumer,
        status="passed",
        base_commit=base_commit,
        detail=(
            "install, audit, "
            f"{len(consumer.candidate_prepare)} preparation(s), and "
            f"{len(consumer.candidate_checks)} check(s) passed"
        ),
        duration_seconds=time.monotonic() - started,
    )


def current_evidence(
    manifest_path: Path,
    fleet_path: Path,
) -> tuple[str, str, str, list[FleetConsumer]]:
    manifest = load_json_object(manifest_path, "pack manifest")
    version = manifest_version(manifest)
    payload = filesystem_payload_digest(manifest_path)
    try:
        fleet_bytes = fleet_path.read_bytes()
    except OSError as error:
        raise FleetConfigError(f"cannot read fleet manifest {fleet_path}: {error}") from None
    return version, payload, fleet_manifest_digest(fleet_bytes), load_fleet_consumers(fleet_path)


def ledger_content(
    *,
    version: str,
    payload_digest: str,
    fleet_digest: str,
    results: list[CandidateResult],
) -> dict[str, object]:
    return {
        "schemaVersion": CANDIDATE_LEDGER_SCHEMA_VERSION,
        "validatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "packVersion": version,
        "payloadDigest": payload_digest,
        "fleetManifestDigest": fleet_digest,
        "consumers": [
            {
                "name": result.consumer.name,
                "github": result.consumer.github,
                "baseCommit": result.base_commit,
                "status": result.status,
                "prepares": [
                    list(command) for command in result.consumer.candidate_prepare
                ],
                "checks": [list(command) for command in result.consumer.candidate_checks],
            }
            for result in results
        ],
    }


def write_ledger(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
            errors="strict",
        )
        os.replace(temporary, path)
    except (OSError, UnicodeError) as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise FleetConfigError(f"cannot write candidate ledger {path}: {error}") from None


def check_ledger(
    *,
    manifest_path: Path,
    fleet_path: Path,
    ledger_path: Path,
) -> list[str]:
    version, payload, fleet_digest, consumers = current_evidence(
        manifest_path, fleet_path
    )
    try:
        ledger = load_json_object(ledger_path, "candidate ledger")
    except FleetConfigError as error:
        return [str(error)]
    return validate_candidate_ledger(
        ledger,
        expected_version=version,
        expected_payload_digest=payload,
        expected_fleet_digest=fleet_digest,
        consumers=consumers,
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install the current pack candidate into disposable fleet clones, "
            "run compatibility checks, and write an all-pass release ledger."
        )
    )
    parser.add_argument("--fleet", type=Path, default=DEFAULT_FLEET_MANIFEST)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_PACK_MANIFEST)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--consumer",
        action="append",
        help="limit diagnostics to this consumer; partial runs never write the ledger",
    )
    parser.add_argument(
        "--check-ledger",
        action="store_true",
        help="verify existing evidence without cloning or running consumer checks",
    )
    parser.add_argument("--json", action="store_true", help="print JSON results")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.check_ledger:
            if args.consumer:
                raise FleetConfigError("--check-ledger cannot be combined with --consumer")
            errors = check_ledger(
                manifest_path=args.manifest,
                fleet_path=args.fleet,
                ledger_path=args.ledger,
            )
            if errors:
                for error in errors:
                    print(f"candidate ledger error: {error}", file=sys.stderr)
                return 1
            print("candidate ledger: valid for the current pack payload and fleet")
            return 0

        version, payload, fleet_digest, consumers = current_evidence(
            args.manifest, args.fleet
        )
        selected = set(args.consumer or [])
        if selected:
            known = {consumer.name for consumer in consumers}
            unknown = sorted(selected - known)
            if unknown:
                raise FleetConfigError(
                    f"unknown fleet consumer(s): {', '.join(unknown)}"
                )
            consumers = [consumer for consumer in consumers if consumer.name in selected]

        with tempfile.TemporaryDirectory(prefix="sd-pack-fleet-candidate-") as tempdir:
            work_root = Path(tempdir)
            results = [
                validate_consumer(
                    consumer,
                    pack_root=args.manifest.resolve().parent,
                    work_root=work_root,
                    python_executable=Path(sys.executable),
                )
                for consumer in consumers
            ]

        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "name": result.consumer.name,
                            "github": result.consumer.github,
                            "rolloutPriority": result.consumer.rollout_priority,
                            "status": result.status,
                            "baseCommit": result.base_commit,
                            "durationSeconds": round(result.duration_seconds, 2),
                            "detail": result.detail,
                        }
                        for result in results
                    ],
                    indent=2,
                )
            )
        else:
            print(f"sd-ai-command-pack candidate: {version}")
            for result in results:
                print(
                    f"{result.status:7} P{result.consumer.rollout_priority:02d} "
                    f"{result.consumer.github} ({result.duration_seconds:.1f}s)"
                )
                print(f"  {result.detail}")

        failures = [result for result in results if result.status != "passed"]
        if failures:
            print(
                f"candidate validation failed for {len(failures)} consumer(s); "
                "ledger was not updated",
                file=sys.stderr,
            )
            return 1
        if selected:
            print("candidate diagnostics passed; partial run did not update the ledger")
            return 0

        write_ledger(
            args.ledger,
            ledger_content(
                version=version,
                payload_digest=payload,
                fleet_digest=fleet_digest,
                results=results,
            ),
        )
        print(f"candidate ledger: wrote {args.ledger}")
        return 0
    except FleetConfigError as error:
        print(f"candidate validation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
