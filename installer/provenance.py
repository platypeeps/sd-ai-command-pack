"""Install receipts: provenance hashes for vouching and the installed-targets record."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

from installer.fileops import (
    VOUCHABLE_STATUSES,
    InstallResult,
    atomic_write_text,
    generated_pack_file,
)
from installer.manifest import (
    PackFile,
    read_text_strict,
    target_destination,
)
from installer.registry import (
    FORCE_PRESERVED_TARGETS,
    INSTALLED_TARGETS_FILE,
    MANAGED_BLOCK_KIND,
    PACK_MANIFEST_FILE,
    PROVENANCE_FILE,
    TRELLIS_GITIGNORE_TARGET,
)


def installed_targets_set(
    selected: list[PackFile],
    extra_targets: Iterable[Path] = (),
) -> set[str]:
    """Return the set of POSIX target paths the install records as installed.

    Shared by the receipt content and provenance coverage so the "provenance
    coverage == receipt contents" invariant is structural, not coincidental.
    """
    targets = {file.target.as_posix() for file in selected}
    targets.update(target.as_posix() for target in extra_targets)
    targets.add(INSTALLED_TARGETS_FILE.as_posix())
    return targets


def installed_targets_content(
    selected: list[PackFile],
    *,
    extra_targets: Iterable[Path] = (),
) -> str:
    targets = installed_targets_set(selected, extra_targets)
    return "\n".join(sorted(targets)) + "\n"


PROVENANCE_EXCLUDED_KINDS = {
    MANAGED_BLOCK_KIND,
    "generated-gitignore",
    "generated-manifest",
    "generated-pack-manifest",
    "generated-provenance",
}


def read_existing_provenance_files(target: Path) -> dict[str, str]:
    provenance = target_destination(target, PROVENANCE_FILE)
    # A symlinked provenance is never trusted (mirrors the audit contract);
    # ignoring it here means the atomic rewrite below replaces the symlink
    # with a regular file instead of following it.
    if provenance.is_symlink() or not provenance.is_file():
        return {}
    try:
        payload = json.loads(provenance.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError):
        return {}
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, dict):
        return {}
    return {
        key: value
        for key, value in files.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def read_existing_provenance_files_for_remove(target: Path) -> dict[str, str]:
    try:
        return read_existing_provenance_files(target)
    except SystemExit:
        return {}


def never_vouched_targets(files: list[PackFile]) -> set[str]:
    """Targets provenance must never vouch, whatever a prior file claims.

    Force-preserved targets are user-tunable, managed blocks are shared
    ownership, and generated files describe the install itself; a
    hand-edited provenance entry for any of them would turn legitimate
    local content into a false drift failure.
    """
    return {
        *(path.as_posix() for path in FORCE_PRESERVED_TARGETS),
        *(
            file.target.as_posix()
            for file in files
            if file.kind == MANAGED_BLOCK_KIND
        ),
        INSTALLED_TARGETS_FILE.as_posix(),
        PACK_MANIFEST_FILE.as_posix(),
        PROVENANCE_FILE.as_posix(),
        TRELLIS_GITIGNORE_TARGET.as_posix(),
    }


def provenance_content(
    manifest: dict,
    results: list[InstallResult],
    *,
    existing_files: dict[str, str],
    receipt_targets: set[str],
    never_vouched: set[str],
) -> str:
    # Entries survive for targets still recorded in the receipt so a
    # filtered or partially-skipped run does not shrink coverage; this
    # run's vouched installs overwrite their entries. Never-vouched
    # targets are dropped from prior content too, so a hand-edited
    # provenance file cannot vouch them in through the merge.
    files = {
        key: value
        for key, value in existing_files.items()
        if key in receipt_targets and key not in never_vouched
    }
    # One manifest source can back many targets (a shared skill installs to
    # ~11 platform paths), so hash each distinct source once per call instead
    # of re-reading it for every target that shares it.
    source_digests: dict[Path, str] = {}
    for result in results:
        file = result.file
        if file.kind in PROVENANCE_EXCLUDED_KINDS:
            continue
        # Every status that ends with the target byte-equal to the template
        # is vouchable — including "overwritten" (--force over drifted
        # content), which single-pass refreshes produce for every changed
        # file. Excluded: "preserved" (user content) and "conflict" (target
        # left untouched).
        if result.status not in VOUCHABLE_STATUSES:
            continue
        if file.target.as_posix() in never_vouched:
            continue
        digest = source_digests.get(file.source)
        if digest is None:
            digest = hashlib.sha256(file.source.read_bytes()).hexdigest()
            source_digests[file.source] = digest
        files[file.target.as_posix()] = f"sha256:{digest}"
    payload = {
        "pack": manifest["name"],
        "version": manifest["version"],
        "files": dict(sorted(files.items())),
    }
    return json.dumps(payload, indent=2) + "\n"


def _install_generated_text_file(
    file: PackFile,
    target: Path,
    content: str,
    *,
    dry_run: bool,
) -> InstallResult:
    """Write a generated pack file: unchanged / updated / created (dry-run safe)."""
    destination = target_destination(target, file.target)
    if destination.exists():
        current = read_text_strict(destination, str(file.target))
        if current == content:
            return InstallResult(file, "unchanged")
        if not dry_run:
            atomic_write_text(destination, content)
        return InstallResult(file, "updated")

    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, content)
    return InstallResult(file, "created")


def install_provenance_file(
    manifest: dict,
    results: list[InstallResult],
    target: Path,
    *,
    receipt_targets: set[str],
    never_vouched: set[str],
    dry_run: bool,
) -> InstallResult:
    file = generated_pack_file("generated-provenance", PROVENANCE_FILE)
    content = provenance_content(
        manifest,
        results,
        existing_files=read_existing_provenance_files(target),
        receipt_targets=receipt_targets,
        never_vouched=never_vouched,
    )
    return _install_generated_text_file(file, target, content, dry_run=dry_run)


def installed_pack_manifest_content(manifest: dict) -> str:
    return json.dumps(manifest, indent=2) + "\n"


def install_pack_manifest_file(
    manifest: dict,
    target: Path,
    *,
    dry_run: bool,
) -> InstallResult:
    file = generated_pack_file("generated-pack-manifest", PACK_MANIFEST_FILE)
    content = installed_pack_manifest_content(manifest)
    return _install_generated_text_file(file, target, content, dry_run=dry_run)


def read_existing_installed_targets(target: Path) -> set[str]:
    receipt = target_destination(target, INSTALLED_TARGETS_FILE)
    if not receipt.is_file():
        return set()
    try:
        content = receipt.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise SystemExit(
            f"error: cannot read installed-targets receipt {receipt}: {error}"
        ) from None
    entries: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            entries.add(line)
    return entries


def read_existing_installed_targets_for_remove(target: Path) -> set[str]:
    try:
        return read_existing_installed_targets(target)
    except (OSError, SystemExit):
        return set()


def is_gitignored_path(target: Path, relative_path: str) -> bool:
    """True when git confirms the path is ignored in the target repo.

    Missing git, a non-repo target, and git errors all return False, so
    callers keep the fail-closed drop behavior for those cases.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(target), "check-ignore", "-q", "--", relative_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def preserved_receipt_targets(
    target: Path,
    existing: set[str],
    skipped: list[tuple[PackFile, str]],
) -> list[tuple[Path, str]]:
    """Receipt entries to keep for platforms skipped in this checkout only.

    Platform markers and anchors can live on gitignored paths (the claude
    adapter's all do), so a refresh from a fresh checkout must not drop
    entries another checkout legitimately installed. Detection and
    --platform filter skips always preserve; anchor skips preserve only
    when the anchor is gitignored here (a tracked-but-removed anchor reads
    as an intentional platform removal).
    """
    preserved: list[tuple[Path, str]] = []
    for file, reason in skipped:
        if file.target.as_posix() not in existing:
            continue
        keep = reason == "platform not selected" or reason.startswith("active Trellis")
        if not keep and reason.startswith("anchor "):
            # Check the target path, not the anchor: directory ignore
            # patterns like `.claude/` match a file below the directory but
            # not the bare, nonexistent directory path itself.
            keep = is_gitignored_path(target, file.target.as_posix())
        if keep:
            preserved.append((file.target, file.platform))
    return preserved


def install_installed_targets_file(
    selected: list[PackFile],
    target: Path,
    *,
    dry_run: bool,
    extra_targets: Iterable[Path] = (),
) -> InstallResult:
    file = generated_pack_file("generated-manifest", INSTALLED_TARGETS_FILE)
    content = installed_targets_content(selected, extra_targets=extra_targets)
    return _install_generated_text_file(file, target, content, dry_run=dry_run)


__all__ = [
    "PROVENANCE_EXCLUDED_KINDS",
    "install_installed_targets_file",
    "install_pack_manifest_file",
    "install_provenance_file",
    "installed_pack_manifest_content",
    "installed_targets_content",
    "installed_targets_set",
    "is_gitignored_path",
    "never_vouched_targets",
    "preserved_receipt_targets",
    "provenance_content",
    "read_existing_installed_targets",
    "read_existing_installed_targets_for_remove",
    "read_existing_provenance_files",
    "read_existing_provenance_files_for_remove",
]
