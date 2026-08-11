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
INSTALLED_MANIFEST_FILE = Path(".sd-ai-command-pack/manifest.json")
INSTALLED_TARGETS_FILE = Path(".sd-ai-command-pack/installed-targets.txt")
THIN_MODE = "thin"
# How many missing paths a damaged-residual detail names before it stops. The
# operator needs enough to recognize what broke, not the whole list; the audit
# command printed alongside it reports every one.
RESIDUAL_SAMPLE = 3


@dataclass(frozen=True)
class FleetPreflightResult:
    consumer: FleetConsumer
    repo_path: Path
    status: str
    installed_version: str | None
    target_version: str
    detail: str
    mode: str | None = None
    installed_platforms: tuple[str, ...] = ()


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


def _read_receipt_object(repo_path: Path, receipt: Path) -> dict:
    """One consumer-side JSON receipt, or an empty mapping.

    Every unreadable shape collapses to `{}`: preflight decides where a
    consumer is routed, and a receipt it cannot parse must land in
    `refresh-needed` rather than raise out of a fleet-wide sweep.

    A symlink is refused rather than followed, matching the unresolved
    `is_symlink()` check `_receipt_declares_thin` and the install audit's
    `installed_mode` make on the same paths. That check matters more here than
    anywhere else: preflight walks a whole fleet of checkouts it did not write,
    so a receipt that is a link is a way out of the checkout it was handed.
    """
    path = repo_path / receipt
    try:
        if path.is_symlink() or not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_provenance(repo_path: Path) -> dict:
    """The consumer's provenance receipt, or an empty mapping."""
    return _read_receipt_object(repo_path, PROVENANCE_FILE)


def read_installed_version(repo_path: Path) -> str | None:
    version = read_provenance(repo_path).get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def read_installed_mode(repo_path: Path) -> tuple[str | None, tuple[str, ...]]:
    """The thin pin's mode and platform set, or `(None, ())`.

    Only `mode: "thin"` is recognized as the mode; an absent or unrecognized
    value reports None so a guess never relaxes the fat contract.

    Both thin witnesses are read, in `thin_pin_state`'s order: the installed
    `manifest.json` first, provenance second. Reading provenance alone would
    miss a half-converted consumer whose manifest survived and whose
    provenance did not -- and that consumer is exactly the one that must not
    be handed a `--platform` repair command, because `thin_pin_state` sees the
    manifest witness and the thin-aware refresh rejects the flag with exit 2.

    The platform set has only one home, the provenance pin, so a thin
    consumer whose provenance is gone reports `()` rather than a guess. That
    is not a downgrade: `()` makes the caller print the registry's platforms
    for information while the thin mode still suppresses the `--platform`
    flag itself.
    """
    provenance = read_provenance(repo_path)
    manifest_declares_thin = (
        _read_receipt_object(repo_path, INSTALLED_MANIFEST_FILE).get("mode")
        == THIN_MODE
    )
    if not manifest_declares_thin and provenance.get("mode") != THIN_MODE:
        return None, ()
    platforms = provenance.get("platforms")
    if not isinstance(platforms, list):
        return THIN_MODE, ()
    return THIN_MODE, tuple(
        sorted(entry for entry in platforms if isinstance(entry, str) and entry)
    )


def read_recorded_targets(repo_path: Path) -> tuple[str, ...]:
    """The paths the consumer's install receipt records, or `()`.

    Symlinked and non-file receipts are refused for the same reason
    `_read_receipt_object` refuses them, and with more at stake: every line
    read here becomes a filesystem probe below, so a linked receipt would aim
    those probes with content from outside the checkout.
    """
    receipt = repo_path / INSTALLED_TARGETS_FILE
    try:
        if receipt.is_symlink() or not receipt.is_file():
            return ()
        content = receipt.read_text(encoding="utf-8", errors="strict")
    except (FileNotFoundError, OSError, UnicodeError):
        return ()
    return tuple(
        line
        for line in (raw.strip() for raw in content.splitlines())
        if line and not line.startswith("#")
    )


def missing_recorded_targets(repo_path: Path) -> tuple[str, ...]:
    """Recorded targets that are no longer on disk.

    Absolute and parent-escaping entries are skipped rather than stat'ed: a
    receipt is consumer-side content, and preflight walks a whole fleet, so
    it must never follow one out of the checkout it was handed.
    """
    missing: list[str] = []
    for entry in read_recorded_targets(repo_path):
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        if not (repo_path / candidate).exists():
            missing.append(entry)
    return tuple(missing)


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
    mode, installed_platforms = read_installed_mode(repo_path)
    if installed_version == target_version:
        # R20-C6. Version equality is the fat contract's evidence of health,
        # and it does not carry over to a thin consumer. On a fat checkout a
        # deleted surface is visible to the audit's manifest-derived
        # completeness check, which a thin install deliberately skips -- for a
        # converted consumer the receipt *is* the allowlist, so a residual
        # file that went missing looks exactly like a machine surface the
        # conversion was supposed to remove. Nothing else in the sweep can
        # tell those apart, so skipping on version alone here is what would
        # leave a damaged thin consumer unrepaired indefinitely.
        damaged = missing_recorded_targets(repo_path) if mode == THIN_MODE else ()
        if not damaged:
            return FleetPreflightResult(
                consumer=consumer,
                repo_path=repo_path,
                status="at-target",
                installed_version=installed_version,
                target_version=target_version,
                detail="skip; already at target version",
                mode=mode,
                installed_platforms=installed_platforms,
            )
        sample = ", ".join(damaged[:RESIDUAL_SAMPLE])
        if len(damaged) > RESIDUAL_SAMPLE:
            sample += f", +{len(damaged) - RESIDUAL_SAMPLE} more"
        return FleetPreflightResult(
            consumer=consumer,
            repo_path=repo_path,
            status="residual-damaged",
            installed_version=installed_version,
            target_version=target_version,
            detail=(
                f"repair needed; at target but {len(damaged)} recorded "
                f"target(s) are missing: {sample}"
            ),
            mode=mode,
            installed_platforms=installed_platforms,
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
        mode=mode,
        installed_platforms=installed_platforms,
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
    # A thin consumer's platform set is owned by its pin, and a thin-aware
    # refresh rejects `--platform` outright rather than re-deriving the
    # residual from a set the registry happens to carry. Emitting the
    # registry's platforms here would print a repair command that exits 2
    # every time -- the printed command has to be the one that works.
    if result.mode != THIN_MODE:
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
                            "mode": result.mode,
                            "installedPlatforms": list(result.installed_platforms),
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
            # The pinned platform set, when there is one: for a thin consumer
            # the registry's list is what it was converted *from*, and a row
            # that prints it reads as though those surfaces are installed.
            platforms = result.installed_platforms or result.consumer.platforms
            mode = f"; mode: {result.mode}" if result.mode else ""
            print(
                f"{result.status:19} P{result.consumer.rollout_priority:02d} "
                f"{result.consumer.github} "
                f"(installed: {installed}{mode}; platforms: "
                f"{', '.join(platforms)})"
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
