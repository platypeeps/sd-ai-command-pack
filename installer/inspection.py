"""Read-only install status, audit orchestration, and report rendering."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from installer.fileops import InstallResult, RemoveResult
from installer.registry import (
    ACTIVE_TRELLIS_PLATFORM_MARKERS,
    INSTALLED_TARGETS_FILE,
    PACK_MANIFEST_FILE,
    PROVENANCE_FILE,
    ROOT,
)
from installer.status import InstallStatus, RemoveStatus

INSPECTION_SCHEMA_VERSION = 1
REFRESH_REQUIRED_EXIT = 3
AUDIT_TIMEOUT_SECONDS = 60
STABLE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

_RECEIPT_PATHS = (PACK_MANIFEST_FILE, PROVENANCE_FILE, INSTALLED_TARGETS_FILE)
_CHANGE_INSTALL_STATUSES = frozenset(
    {
        InstallStatus.CREATED,
        InstallStatus.UPDATED,
        InstallStatus.OVERWRITTEN,
        InstallStatus.CONFLICT,
        InstallStatus.SYMLINK_CONFLICT,
    }
)
_CHANGE_REMOVE_STATUSES = frozenset(
    {
        RemoveStatus.UPDATED,
        RemoveStatus.REMOVED,
        RemoveStatus.WOULD_UPDATE,
        RemoveStatus.WOULD_REMOVE,
        RemoveStatus.RETIRED,
        RemoveStatus.RETIRED_PRESERVED,
        RemoveStatus.WOULD_RETIRE,
    }
)


@dataclass(frozen=True)
class ReceiptState:
    """Validated installed receipt state used by inspection reports."""

    present: bool
    installed_version: str | None
    targets: frozenset[str]
    platforms: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    """Captured install-audit outcome."""

    requested: bool
    status: str
    exit_code: int | None
    output: str


@dataclass(frozen=True)
class InspectionReport:
    """Stable status/check report independent of output format."""

    pack: str
    target: Path
    source_version: str
    installed_version: str | None
    version_relation: str
    state: str
    installed_platforms: tuple[str, ...]
    active_platforms: tuple[str, ...]
    counts: dict[str, int]
    change_count: int
    reasons: tuple[str, ...]
    audit: AuditResult

    def as_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": INSPECTION_SCHEMA_VERSION,
            "pack": self.pack,
            "target": str(self.target),
            "sourceVersion": self.source_version,
            "installedVersion": self.installed_version,
            "versionRelation": self.version_relation,
            "state": self.state,
            "platforms": {
                "installed": list(self.installed_platforms),
                "active": list(self.active_platforms),
            },
            "counts": self.counts,
            "changeCount": self.change_count,
            "reasons": list(self.reasons),
            "audit": {
                "requested": self.audit.requested,
                "status": self.audit.status,
                "exitCode": self.audit.exit_code,
                "output": self.audit.output,
            },
        }


def _load_json_object(path: Path, label: str, errors: list[str]) -> dict | None:
    if path.is_symlink() or not path.is_file():
        errors.append(f"{label} is missing or is not a regular file: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as error:
        errors.append(f"cannot read {label} {path}: {error}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label} must contain a JSON object: {path}")
        return None
    return payload


def _safe_receipt_target(value: str) -> bool:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return bool(value) and not (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or ".." in windows.parts
    )


def _read_target_receipt(path: Path, errors: list[str]) -> frozenset[str]:
    if path.is_symlink() or not path.is_file():
        errors.append(f"installed-targets receipt is missing or invalid: {path}")
        return frozenset()
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as error:
        errors.append(f"cannot read installed-targets receipt {path}: {error}")
        return frozenset()

    entries: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        if not _safe_receipt_target(value):
            errors.append(
                f"installed-targets receipt has unsafe entry on line {line_number}: "
                f"{value!r}"
            )
            continue
        entries.append(value)
    if len(entries) != len(set(entries)):
        errors.append("installed-targets receipt contains duplicate entries")
    return frozenset(entries)


def _manifest_platforms(
    payload: dict | None, targets: frozenset[str], errors: list[str]
) -> tuple[str | None, tuple[str, ...]]:
    if payload is None:
        return None, ()
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        errors.append("installed pack manifest is missing a string version")
        version = None
    files = payload.get("files")
    if not isinstance(files, list):
        errors.append("installed pack manifest is missing its files array")
        return version, ()
    platforms: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            errors.append("installed pack manifest contains a non-object file entry")
            continue
        target = entry.get("target")
        platform = entry.get("platform")
        if not isinstance(target, str):
            errors.append("installed pack manifest file entry has a non-string target")
            continue
        if not isinstance(platform, str):
            errors.append("installed pack manifest file entry has a non-string platform")
            continue
        if target in targets and platform != "shared":
            platforms.add(platform)
    return version, tuple(sorted(platforms))


def _validate_provenance(
    target: Path,
    payload: dict | None,
    installed_version: str | None,
    targets: frozenset[str],
    errors: list[str],
) -> None:
    if payload is None:
        return
    if payload.get("pack") != "sd-ai-command-pack":
        errors.append("installed provenance has an unexpected pack name")
    if installed_version is not None and payload.get("version") != installed_version:
        errors.append("installed manifest and provenance versions do not match")
    files = payload.get("files")
    if not isinstance(files, dict):
        errors.append("installed provenance is missing its files object")
        return
    for relative, recorded in files.items():
        if not isinstance(relative, str) or not _safe_receipt_target(relative):
            errors.append(f"installed provenance has an unsafe target: {relative!r}")
            continue
        if relative not in targets:
            errors.append(f"provenance target is absent from installed-targets: {relative}")
        if not isinstance(recorded, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", recorded
        ):
            errors.append(f"provenance target has an invalid digest: {relative}")
            continue
        destination = target / relative
        if destination.is_symlink() or not destination.is_file():
            errors.append(f"vouched target is missing or invalid: {relative}")
            continue
        try:
            actual = "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
        except OSError as error:
            errors.append(f"cannot read vouched target {relative}: {error}")
            continue
        if actual != recorded:
            errors.append(f"vouched target content drifted: {relative}")


def inspect_receipts(target: Path) -> ReceiptState:
    """Read and validate installed receipts without mutating the target."""
    occupied = [
        path
        for path in _RECEIPT_PATHS
        if (target / path).exists() or (target / path).is_symlink()
    ]
    if not occupied:
        return ReceiptState(False, None, frozenset(), (), ())

    errors: list[str] = []
    if len(occupied) != len(_RECEIPT_PATHS):
        missing = sorted(
            path.as_posix() for path in _RECEIPT_PATHS if path not in occupied
        )
        errors.append(
            f"installed pack footprint is incomplete; missing: {', '.join(missing)}"
        )

    manifest_payload = _load_json_object(
        target / PACK_MANIFEST_FILE, "installed pack manifest", errors
    )
    provenance_payload = _load_json_object(
        target / PROVENANCE_FILE, "installed provenance", errors
    )
    targets = _read_target_receipt(target / INSTALLED_TARGETS_FILE, errors)
    installed_version, platforms = _manifest_platforms(
        manifest_payload, targets, errors
    )

    for relative in sorted(targets):
        destination = target / relative
        if destination.is_symlink() or not destination.is_file():
            errors.append(f"installed target is missing or invalid: {relative}")
    _validate_provenance(
        target, provenance_payload, installed_version, targets, errors
    )
    return ReceiptState(
        True,
        installed_version,
        targets,
        platforms,
        tuple(dict.fromkeys(errors)),
    )


def active_platforms(target: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            platform
            for platform, markers in ACTIVE_TRELLIS_PLATFORM_MARKERS.items()
            if any((target / marker).is_file() for marker in markers)
        )
    )


def version_relation(installed: str | None, source: str) -> str:
    if installed is None:
        return "not-installed"
    if not STABLE_VERSION_PATTERN.fullmatch(installed) or not (
        STABLE_VERSION_PATTERN.fullmatch(source)
    ):
        return "unknown"
    installed_key = tuple(int(part) for part in installed.split("."))
    source_key = tuple(int(part) for part in source.split("."))
    if installed_key < source_key:
        return "behind"
    if installed_key > source_key:
        return "ahead"
    return "current"


def run_install_audit(target: Path) -> AuditResult:
    """Run the shipped audit as the single authority for full integrity checks."""
    command = [
        sys.executable,
        str(ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
        "--repo",
        str(target),
        "--upstream-manifest",
        str(ROOT),
    ]
    env = os.environ.copy()
    env.pop("SD_AI_COMMAND_PACK_INSTALL_AUDIT", None)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=AUDIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        if output and not output.endswith("\n"):
            output += "\n"
        return AuditResult(True, "error", None, f"{output}audit timed out".strip())
    except OSError as error:
        return AuditResult(True, "error", None, f"cannot run install audit: {error}")
    return AuditResult(
        True,
        "passed" if result.returncode == 0 else "failed",
        result.returncode,
        result.stdout.rstrip(),
    )


def not_requested_audit(
    *, applicable: bool = True, requested: bool = False
) -> AuditResult:
    status = "not-requested" if applicable else "not-applicable"
    return AuditResult(requested, status, None, "")


def build_report(
    *,
    manifest_data: dict,
    target: Path,
    receipts: ReceiptState,
    install_results: list[InstallResult],
    retired_results: list[RemoveResult],
    audit: AuditResult,
) -> InspectionReport:
    source_version = str(manifest_data["version"])
    relation = version_relation(receipts.installed_version, source_version)
    statuses = [str(result.status) for result in install_results]
    statuses.extend(str(result.status) for result in retired_results)
    counts = dict(sorted(Counter(statuses).items()))
    change_count = sum(
        result.status in _CHANGE_INSTALL_STATUSES for result in install_results
    ) + sum(result.status in _CHANGE_REMOVE_STATUSES for result in retired_results)

    reasons: list[str] = list(receipts.errors)
    if receipts.errors:
        state = "invalid"
    elif not receipts.present:
        state = "not-installed"
        reasons.append("No installed sd-ai-command-pack footprint was found.")
    elif audit.status in {"failed", "error"}:
        state = "invalid"
        reasons.append("The structural install audit did not pass.")
    elif relation != "current" or change_count:
        state = "refresh-required"
        if relation != "current":
            reasons.append(f"Installed version is {relation} the source version.")
        if change_count:
            reasons.append(f"A refresh would change {change_count} target(s).")
    else:
        state = "current"
        reasons.append("Installed payload and source checkout are current.")

    return InspectionReport(
        pack=str(manifest_data["name"]),
        target=target,
        source_version=source_version,
        installed_version=receipts.installed_version,
        version_relation=relation,
        state=state,
        installed_platforms=receipts.platforms,
        active_platforms=active_platforms(target),
        counts=counts,
        change_count=change_count,
        reasons=tuple(reasons),
        audit=audit,
    )


def render_human(report: InspectionReport) -> str:
    installed = report.installed_version or "not installed"
    installed_platforms = ", ".join(report.installed_platforms) or "shared-only"
    active = ", ".join(report.active_platforms) or "none detected"
    lines = [
        f"{report.pack} {report.source_version}",
        f"target: {report.target}",
        f"state: {report.state}",
        f"installed version: {installed}",
        f"version relation: {report.version_relation}",
        f"platforms: installed={installed_platforms}; active={active}",
        f"planned changes: {report.change_count}",
        f"audit: {report.audit.status}",
    ]
    if report.counts:
        lines.append(
            "result counts: "
            + ", ".join(f"{key}={value}" for key, value in report.counts.items())
        )
    if report.reasons:
        lines.append("reasons:")
        lines.extend(f"- {reason}" for reason in report.reasons)
    if report.audit.output and report.audit.status != "passed":
        lines.append("audit output:")
        lines.extend(f"  {line}" for line in report.audit.output.splitlines())
    return "\n".join(lines)


def render_json(report: InspectionReport) -> str:
    return json.dumps(report.as_dict(), indent=2, sort_keys=True)


def report_exit_code(report: InspectionReport, *, check: bool) -> int:
    if report.state == "invalid":
        return 1
    if check and report.state != "current":
        return REFRESH_REQUIRED_EXIT
    return 0


__all__ = [
    "AUDIT_TIMEOUT_SECONDS",
    "AuditResult",
    "INSPECTION_SCHEMA_VERSION",
    "InspectionReport",
    "REFRESH_REQUIRED_EXIT",
    "ReceiptState",
    "active_platforms",
    "build_report",
    "inspect_receipts",
    "not_requested_audit",
    "render_human",
    "render_json",
    "report_exit_code",
    "run_install_audit",
    "version_relation",
]
