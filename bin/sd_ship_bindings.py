"""Complete local gate manifests shared by both review identity modes."""

from __future__ import annotations

import hashlib
import pathlib

import sd_lib
from sd_ship_history import digest
from sd_ship_remote import Refusal

BIN = pathlib.Path(__file__).resolve().parent
# Review dispatch, report validation, history, identity, and clearance all matter.
# Keep the original members even where an indirect dependency appears redundant.
# The tuple is hand-maintained, so a module the gate grows a dependency on is
# a silent gap until a line is added here -- `sd_protection.py` was one for a
# day (sd:1327 review, finding 3). `tests/test_sd_workflow_state.py` now walks
# `sd-ship`'s imports and fails naming any that this tuple lacks.
REVIEW_TOOL_FILES = (
    "sd-review", "sd_lib.py", "sd_registry.py", "sd_route.py", "sd_codex.py", "sd-check", "sd-docs-lint",
    "sd-ship", "sd_ship_dispositions.py", "sd_ship_remote.py", "sd_ship_review.py",
    "sd_ship_history.py", "sd_ship_identity.py", "sd_ship_item.py", "sd_ship_no_item.py",
    "sd_ship_evidence.py", "sd_ship_bindings.py", "sd_ship_workflow.py", "sd_protection.py",
    "sd_check_receipts.py", "sd_review_material.py", "sd_review_readiness.py",
)
ADJUDICATOR_POLICY_FILES = (
    "skills/sd-check/SKILL.md", "skills/sd-review/SKILL.md", "skills/sd-ship/SKILL.md",
    "skills/sd-check/references/check-receipts.md", ".claude/rules/sd-planning-adversarial-review.md",
)


def file_hash(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise Refusal(f"required review binding file cannot be read: {path}: {error.strerror}") from None


def tool_files() -> dict:
    return {name: file_hash(BIN / name) for name in REVIEW_TOOL_FILES}


def review_binding(root: pathlib.Path) -> str:
    files = tool_files()
    for name in ("CLAUDE.local.md", ".github/sd-review.json"):
        path = sd_lib.local_block_path(root) if name == sd_lib.LOCAL_FILE_NAME else root / name
        # Preserve item-backed repository-policy I/O errors for existing callers.
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() or path.is_symlink() else "absent"
    files["external_review_policy"] = digest({"path": str(sd_lib.machine_config_path()), "value": sd_lib.core_setting("external_reviews")})
    return digest(files)


def adjudicator_binding(library_file: str) -> str:
    files = tool_files()
    files["sd_db.ship"] = file_hash(pathlib.Path(library_file))
    for name in ADJUDICATOR_POLICY_FILES:
        files[name] = file_hash(BIN.parent / name)
    # Conditional skill references still own acceptance rules. Enumerate their
    # actual inventory so additions and removals also invalidate old clearance.
    for skill in ("sd-check", "sd-review", "sd-ship"):
        for path in sorted((BIN.parent / "skills" / skill / "references").rglob("*.md")):
            files[str(path.relative_to(BIN.parent))] = file_hash(path)
    return digest(files)
