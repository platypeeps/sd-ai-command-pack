"""Part of the sd-ai-command-pack installer package."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from installer.registry import (
    MANAGED_BLOCK_KIND,
    PLATFORMS,
    ROOT,
    TRELLIS_INSTALL_DOCS_URL,
)

MANIFEST_PATH = ROOT / "manifest.json"

@dataclass(frozen=True)
class PackFile:
    platform: str
    kind: str
    source: Path
    target: Path
    anchor: Path | None
    install: str


SUPPORTED_MANIFEST_SCHEMA_VERSION = 1
KNOWN_MANIFEST_KINDS = frozenset(
    {
        "command",
        "config",
        "doc",
        MANAGED_BLOCK_KIND,
        "prompt",
        "script",
        "skill",
        "workflow",
    }
)


def load_manifest() -> tuple[dict, list[PackFile]]:
    try:
        raw = json.loads(read_text_strict(MANIFEST_PATH, "manifest"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"error: manifest is not valid JSON: {error}") from None
    if not isinstance(raw, dict):
        raise SystemExit(
            f"error: manifest must be a JSON object, got {type(raw).__name__}"
        )
    schema_version = raw.get("schemaVersion", 1)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise SystemExit(
            f"error: manifest schemaVersion must be an integer, got {schema_version!r}"
        )
    if schema_version > SUPPORTED_MANIFEST_SCHEMA_VERSION:
        raise SystemExit(
            f"error: manifest schemaVersion {schema_version} is newer than this "
            f"installer supports ({SUPPORTED_MANIFEST_SCHEMA_VERSION}); update "
            "the pack checkout before installing"
        )
    requires_trellis = raw.get("requiresTrellis", True)
    if not isinstance(requires_trellis, bool):
        raise SystemExit(
            "error: manifest requiresTrellis must be a boolean, got "
            f"{requires_trellis!r}"
        )
    files_value = raw.get("files", [])
    if not isinstance(files_value, list):
        raise SystemExit(
            f"error: manifest 'files' must be an array, got "
            f"{type(files_value).__name__}"
        )
    files: list[PackFile] = []
    for index, item in enumerate(files_value):
        try:
            files.append(
                PackFile(
                    platform=str(item["platform"]),
                    kind=str(item["kind"]),
                    source=ROOT / str(item["source"]),
                    target=Path(str(item["target"])),
                    anchor=Path(str(item["anchor"])) if item.get("anchor") else None,
                    install=str(item.get("install", "if-anchor-exists")),
                )
            )
        except KeyError as error:
            raise SystemExit(
                f"error: manifest files[{index}] is missing required field "
                f"{error.args[0]!r}"
            ) from None
        except TypeError:
            raise SystemExit(
                f"error: manifest files[{index}] must be an object with "
                "platform/kind/source/target fields"
            ) from None
    return raw, files


def validate_manifest(files: list[PackFile]) -> None:
    seen_targets: set[Path] = set()
    for file in files:
        if file.platform not in PLATFORMS:
            raise SystemExit(f"error: unknown platform {file.platform!r} in manifest")
        if file.kind not in KNOWN_MANIFEST_KINDS:
            raise SystemExit(
                f"error: unknown kind {file.kind!r} in manifest for {file.target} "
                f"(known kinds: {', '.join(sorted(KNOWN_MANIFEST_KINDS))})"
            )
        validate_pack_source(file.source)
        validate_relative_manifest_path("target", file.target)
        if file.anchor is not None:
            validate_relative_manifest_path("anchor", file.anchor)
        if file.target in seen_targets:
            raise SystemExit(f"error: duplicate target in manifest: {file.target}")
        seen_targets.add(file.target)
        if not file.source.is_file():
            raise SystemExit(f"error: missing pack template {file.source}")


def validate_relative_manifest_path(field: str, path: Path) -> None:
    windows_path = PureWindowsPath(str(path))
    if (
        path.is_absolute()
        or bool(windows_path.drive)
        or bool(windows_path.root)
        or ".." in path.parts
        or ".." in windows_path.parts
    ):
        raise SystemExit(f"error: unsafe {field} path in manifest: {path}")


def read_text_strict(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"error: {label} not found: {path}") from None
    except UnicodeDecodeError as error:
        raise SystemExit(f"error: {label} is not valid UTF-8: {path} ({error})") from None
    except OSError as error:
        raise SystemExit(f"error: cannot read {label}: {path} ({error})") from None


def read_text_if_exists(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except UnicodeDecodeError as error:
        raise SystemExit(f"error: {label} is not valid UTF-8: {path} ({error})") from None
    except OSError as error:
        raise SystemExit(f"error: cannot read {label}: {path} ({error})") from None


def system_exit_detail(error: SystemExit) -> str:
    detail = str(error)
    if detail.startswith("error: "):
        detail = detail[len("error: ") :]
    return detail or "operation failed"


def manifest_cli_identity() -> str:
    try:
        raw = json.loads(read_text_strict(MANIFEST_PATH, "manifest"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"error: manifest is not valid JSON: {error}") from None
    name = raw.get("name")
    version = raw.get("version")
    if not isinstance(name, str) or not name.strip():
        raise SystemExit("error: manifest name is missing")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit("error: manifest version is missing")
    return f"{name} {version}"

def validate_pack_source(source: Path) -> None:
    try:
        relative_source = source.relative_to(ROOT)
    except ValueError:
        raise SystemExit(f"error: unsafe source path in manifest: {source}") from None
    validate_relative_manifest_path("source", relative_source)
    try:
        # ROOT is Path(__file__).resolve().parent.parent, i.e. already
        # symlink-resolved and absolute; ROOT.resolve() would be a no-op.
        source.resolve(strict=False).relative_to(ROOT)
    except (OSError, RuntimeError) as error:
        raise SystemExit(
            f"error: cannot resolve source path in manifest: {source} ({error})"
        ) from None
    except ValueError:
        raise SystemExit(f"error: unsafe source path in manifest: {source}") from None


def validate_resolved_target_path(target: Path, path: Path, label: str) -> None:
    try:
        target_root = target.resolve()
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise SystemExit(f"error: cannot resolve {label}: {path} ({error})") from None

    try:
        resolved_path.relative_to(target_root)
    except ValueError:
        raise SystemExit(
            f"error: {label} resolves outside target repo: {path}"
        ) from None


def target_destination(target: Path, relative_path: Path, label: str = "target path") -> Path:
    validate_relative_manifest_path("target", relative_path)
    destination = target / relative_path
    validate_resolved_target_path(target, destination, label)
    return destination


def removal_target_destination(
    target: Path,
    relative_path: Path,
    label: str = "target path",
) -> Path:
    validate_relative_manifest_path("target", relative_path)
    destination = target / relative_path
    validate_resolved_target_path(target, destination.parent, f"{label} parent")
    return destination




def require_target_directory(target: Path) -> None:
    if not target.is_dir():
        raise SystemExit(f"error: target repo not found or not a directory: {target}")


def require_trellis_repo(target: Path) -> None:
    if not (target / ".trellis" / "config.yaml").is_file():
        raise SystemExit(
            f"error: {target} does not look like a Trellis repo "
            "(.trellis/config.yaml not found). Install Trellis and run "
            f"`trellis init` first: {TRELLIS_INSTALL_DOCS_URL}"
        )


__all__ = [
    "KNOWN_MANIFEST_KINDS",
    "MANIFEST_PATH",
    "PackFile",
    "SUPPORTED_MANIFEST_SCHEMA_VERSION",
    "load_manifest",
    "manifest_cli_identity",
    "read_text_if_exists",
    "read_text_strict",
    "removal_target_destination",
    "require_target_directory",
    "require_trellis_repo",
    "system_exit_detail",
    "target_destination",
    "validate_manifest",
    "validate_pack_source",
    "validate_relative_manifest_path",
    "validate_resolved_target_path",
]
