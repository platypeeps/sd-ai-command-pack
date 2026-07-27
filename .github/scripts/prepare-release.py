#!/usr/bin/env python3
"""Prepare an exact sd-ai-command-pack candidate before the final check."""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
SURFACE_CHECK = "scripts/sd-ai-command-pack-surface-check.py"
CANDIDATE_CHECK = "scripts/sd-ai-command-pack-fleet-candidate-check.py"
CANDIDATE_LEDGER = "docs/fleet/candidate-validation.json"
MAX_INPUT_BYTES = 2 * 1024 * 1024
SURFACE_TIMEOUT_SECONDS = 180
COMMAND_TIMEOUT_SECONDS = 300
GIT_TIMEOUT_SECONDS = 60
PAYLOAD_SINGLETONS = frozenset(
    {
        "manifest.json",
        "docs/SD_AI_COMMAND_PACK.md",
        "templates/docs/SD_AI_COMMAND_PACK.md",
    }
)


class ReleasePrepError(RuntimeError):
    """Expected release-preparation failure with a controlled CLI message."""


def _command_text(command: Sequence[str]) -> str:
    return " ".join(command)


def _run_visible(
    root: Path,
    command: Sequence[str],
    *,
    label: str,
    timeout: int | None = COMMAND_TIMEOUT_SECONDS,
) -> None:
    print(f"release prep: {label}", flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleasePrepError(
            f"{label} could not complete: {_command_text(command)}: {error}"
        ) from error
    if result.returncode != 0:
        raise ReleasePrepError(
            f"{label} failed with exit {result.returncode}: {_command_text(command)}"
        )


def _run_surface_check(root: Path, python: str) -> dict[str, object]:
    command = [python, SURFACE_CHECK, "--json"]
    print("release prep: validate shipped-surface closure", flush=True)
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=SURFACE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise ReleasePrepError(f"surface check could not complete: {error}") from error

    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = (result.stderr or result.stdout).strip()[:800]
        suffix = f": {detail}" if detail else ""
        raise ReleasePrepError(
            f"surface check returned invalid JSON at line {error.lineno}{suffix}"
        ) from error
    if not isinstance(report, dict):
        raise ReleasePrepError("surface check JSON must be an object")

    status = report.get("status")
    if not isinstance(status, str):
        raise ReleasePrepError("surface check status must be text")
    expected_exit = {"clean": 0, "failed": 1, "invalid": 2}.get(status)
    if expected_exit is None or result.returncode != expected_exit:
        raise ReleasePrepError(
            "surface check status and exit code disagree: "
            f"status={status!r}, exit={result.returncode}"
        )
    return report


def _candidate_refresh_required(report: Mapping[str, object]) -> bool:
    schema_version = report.get("schemaVersion")
    if type(schema_version) is not int or schema_version != 1:
        raise ReleasePrepError("surface check schemaVersion must be 1")
    if report.get("findingsTruncated") is not False:
        raise ReleasePrepError("surface check findings must be complete")

    changed_paths = report.get("changedPaths")
    if not isinstance(changed_paths, list) or not all(
        isinstance(path, str) and path for path in changed_paths
    ):
        raise ReleasePrepError("surface check changedPaths must be a string array")
    base_ref = report.get("baseRef")
    if base_ref is not None and (
        not isinstance(base_ref, str) or not base_ref.strip()
    ):
        raise ReleasePrepError("surface check baseRef must be null or non-empty text")

    status = report.get("status")
    count = report.get("findingCount")
    findings = report.get("findings")
    counts = report.get("findingCounts")
    if type(count) is not int:
        raise ReleasePrepError("surface check findingCount must be an integer")
    if not isinstance(counts, dict):
        raise ReleasePrepError("surface check findingCounts must be an object")
    if status == "clean":
        if count != 0 or findings != [] or counts != {}:
            raise ReleasePrepError("clean surface report contains findings")
        return False

    if status != "failed" or count != 1 or not isinstance(findings, list):
        raise ReleasePrepError("surface closure must be clean except for stale candidate evidence")
    candidate_count = counts.get("provenance.candidate-stale")
    if (
        len(counts) != 1
        or type(candidate_count) is not int
        or candidate_count != 1
        or len(findings) != 1
    ):
        raise ReleasePrepError("surface closure contains a non-candidate finding")
    finding = findings[0]
    if not isinstance(finding, dict):
        raise ReleasePrepError("surface check finding must be an object")
    expected = {
        "code": "provenance.candidate-stale",
        "path": CANDIDATE_LEDGER,
        "relation": "requires-release-evidence",
    }
    if any(finding.get(field) != value for field, value in expected.items()):
        raise ReleasePrepError("surface closure contains unexpected candidate evidence")
    return True


def _regular_bytes(path: Path, *, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ReleasePrepError(f"cannot read {label} {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise ReleasePrepError(f"{label} must be a regular file: {path}")
    if metadata.st_size > MAX_INPUT_BYTES:
        raise ReleasePrepError(f"{label} exceeds {MAX_INPUT_BYTES} bytes: {path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ReleasePrepError(f"cannot read {label} {path}: {error}") from error


def _json_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReleasePrepError(f"{label} must be valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise ReleasePrepError(f"{label} must be a JSON object")
    return value


def _git_text(root: Path, *args: str) -> str:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise ReleasePrepError(f"git comparison could not complete: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:800]
        suffix = f": {detail}" if detail else ""
        raise ReleasePrepError(
            f"git comparison failed ({result.returncode}): "
            f"{_command_text(command)}{suffix}"
        )
    return result.stdout


def _manifest_version(manifest: Mapping[str, object], *, label: str) -> str:
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ReleasePrepError(f"{label} version must be non-empty text")
    return version.strip()


def _is_payload_path(path: str) -> bool:
    return path in PAYLOAD_SINGLETONS or path.startswith("templates/")


def _validate_release_prerequisites(
    root: Path,
    report: Mapping[str, object],
) -> None:
    changed_paths = report["changedPaths"]
    if not isinstance(changed_paths, list):
        raise ReleasePrepError("surface check changedPaths must be a string array")
    payload_paths = sorted(
        path for path in changed_paths if isinstance(path, str) and _is_payload_path(path)
    )
    if not payload_paths:
        print("release prep: no shipped payload change; version gate not required")
        return

    base_ref = report.get("baseRef")
    if not isinstance(base_ref, str) or not base_ref.strip():
        raise ReleasePrepError(
            "shipped payload changed but no comparison base resolved; "
            "set SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF"
        )
    current_manifest = _json_object(
        _regular_bytes(root / "manifest.json", label="current manifest"),
        label="current manifest",
    )
    base_manifest = _json_object(
        _git_text(root, "show", f"{base_ref}:manifest.json").encode("utf-8"),
        label=f"base manifest at {base_ref}",
    )
    current_version = _manifest_version(current_manifest, label="current manifest")
    base_version = _manifest_version(base_manifest, label=f"base manifest at {base_ref}")
    if current_version == base_version:
        preview = ", ".join(payload_paths[:8])
        if len(payload_paths) > 8:
            preview += f", ... ({len(payload_paths)} total)"
        raise ReleasePrepError(
            "shipped payload changed without a manifest version bump "
            f"relative to {base_ref}: {preview}"
        )

    changelog_bytes = _regular_bytes(root / "CHANGELOG.md", label="changelog")
    try:
        changelog = changelog_bytes.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ReleasePrepError(f"changelog must be valid UTF-8: {error}") from error
    top_heading = next(
        (line.strip() for line in changelog.splitlines() if line.startswith("## ")),
        None,
    )
    expected = re.compile(
        rf"^## {re.escape(current_version)} - \d{{4}}-\d{{2}}-\d{{2}}$"
    )
    if top_heading is None or expected.fullmatch(top_heading) is None:
        found = repr(top_heading) if top_heading else "no release heading"
        raise ReleasePrepError(
            f"manifest version {current_version!r} requires top CHANGELOG.md heading "
            f"'## {current_version} - YYYY-MM-DD'; found {found}"
        )
    print(
        "release prep: shipped payload version gate passed: "
        f"{base_version} -> {current_version}"
    )


def prepare_release(root: Path = ROOT, python: str = sys.executable) -> None:
    _run_visible(
        root,
        [python, ".github/scripts/generate-command-surfaces.py"],
        label="generate command surfaces",
    )
    _run_visible(
        root,
        [python, "install.py", ".", "--force"],
        label="self-sync dogfood install",
    )
    _run_visible(
        root,
        [python, "scripts/sd-ai-command-pack-update-spec-kb.py"],
        label="refresh generated spec knowledge base",
    )

    report = _run_surface_check(root, python)
    refresh_candidate = _candidate_refresh_required(report)
    _validate_release_prerequisites(root, report)
    if not refresh_candidate:
        print("release prep: candidate ledger is current; skipping fleet validation")
        return

    _run_visible(
        root,
        [python, CANDIDATE_CHECK],
        label="validate exact candidate across the full fleet",
        timeout=None,
    )
    final_report = _run_surface_check(root, python)
    if _candidate_refresh_required(final_report):
        raise ReleasePrepError(
            "candidate validation completed but the exact-payload ledger remains stale"
        )
    print("release prep: exact candidate evidence and shipped-surface closure are current")


def main() -> int:
    try:
        prepare_release()
    except ReleasePrepError as error:
        print(f"release prep: failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
