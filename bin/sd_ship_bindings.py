"""Complete local gate manifests shared by both review identity modes."""

from __future__ import annotations

import ast
import hashlib
import pathlib
import sys

import sd_lib
from sd_ship_history import digest
from sd_ship_remote import Refusal

BIN = pathlib.Path(__file__).resolve().parent
# Every file the review gate reads belongs to exactly one class (sd:1834,
# `docs/work/2026-09-29-review-binding-semantics/design.md`).
#
# `verdict` is the code that ran inside the `sd-review` process, plus the argv
# `sd-ship` hands it: it chose the providers, built the prompt, ran the
# deterministic check and parsed the findings. A receipt cannot be re-derived,
# so a change here moves the binding. It is hashed with comments and
# docstrings removed; every other string literal stays, prompt text included.
#
# `gate` and `check` run again on every `prepare` and `merge` against the
# stored report, and the merge gate runs the repository's check again at the
# landing head. A change there already applies to an old receipt, so it stays
# out of the digest. Their hashes are recorded so a moved binding names them.
#
# The tuples are hand-maintained. `tests/test_sd_workflow_state.py` walks the
# imports of `sd-ship`, `sd-review` and `sd-check` and fails naming any module
# that is in no class and not in `IMPORT_EXEMPT` -- `sd_protection.py` was a
# silent gap for a day (sd:1327 review, finding 3), `sd_jev.py` and
# `sd_opencode.py` for longer (sd:1834).
VERDICT_FILES = (
    "sd-review", "sd_lib.py", "sd_registry.py", "sd_route.py", "sd_codex.py",
    "sd_review_material.py", "sd_review_readiness.py", "sd_review_request.py", "sd_review_slots.py", "sd_jev.py", "sd_opencode.py",
)
GATE_FILES = (
    "sd-ship", "sd-docs-lint", "sd_ship_dispositions.py", "sd_ship_remote.py", "sd_ship_review.py",
    "sd_ship_history.py", "sd_ship_identity.py", "sd_ship_item.py", "sd_ship_no_item.py",
    "sd_ship_evidence.py", "sd_ship_bindings.py", "sd_ship_workflow.py", "sd_ship_squash.py", "sd_ship_body.py",
    "sd_ship_hold.py", "sd_protection.py", "sd_local_gate.py", "sd_changelog_merge.py",
)
CHECK_FILES = (
    "sd-check", "sd_check_receipts.py", "sd_gate_slots.py",
    # sd:2041, sd:2072. The gate check sd-review runs, its receipts and its docs-only scope;
    # prepare and the merge gate run them again live.
    "sd_gate_run.py", "sd_gate_receipts.py", "sd_check_scope.py",
)
#: The `verdict` files that parse reviewer output or dispose findings
#: (`parse_findings`, `dispose` and `finish_review` in `sd-review`,
#: `opencode_answer`, `url_response`). An unchanged review request does not
#: make an unchanged verdict when one of these moved, so a moved binding that
#: names one re-reviews instead of replaying `--explain` (sd:1397, option A).
FINDING_FILES = ("sd-review", "sd_opencode.py", "sd_registry.py")
#: Imported by a review tool but never on the review path.
IMPORT_EXEMPT = {
    "sd_setup_github.py": "sd-review imports it only for the `setup-github` subcommand",
    "sd_setup_guard.py": "reached only through sd_setup_github.py",
}
REVIEW_TOOL_FILES = VERDICT_FILES + GATE_FILES + CHECK_FILES
POLICY_FILES = ("CLAUDE.local.md", ".github/sd-review.json")
ADJUDICATOR_POLICY_FILES = (
    "skills/sd-check/SKILL.md", "skills/sd-review/SKILL.md", "skills/sd-ship/SKILL.md",
    "skills/sd-check/references/check-receipts.md", ".claude/rules/sd-planning-adversarial-review.md",
)
#: Names the normalizer. The interpreter is in it because `ast.dump` is only
#: stable within one minor version: a new one moves every binding once, and
#: says so, rather than naming every file.
NORMALIZER = f"ast-docstring-1/py{sys.version_info.major}.{sys.version_info.minor}"
LEGACY_ENTRY = "receipt predates the per-file manifest"


def read_bound(path: pathlib.Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Refusal(f"required review binding file cannot be read: {path}: {error.strerror}") from None


def file_hash(path: pathlib.Path) -> str:
    return hashlib.sha256(read_bound(path)).hexdigest()


def normalized_source(data: bytes) -> str | None:
    """The source's syntax tree without comments, docstrings or layout; None when it does not parse."""
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree, include_attributes=False)


def normalized_hash(path: pathlib.Path) -> str:
    """A file that does not parse is hashed raw, never skipped."""
    data = read_bound(path)
    source = normalized_source(data)
    if source is None:
        return "raw:" + hashlib.sha256(data).hexdigest()
    return "ast:" + hashlib.sha256(source.encode()).hexdigest()


def tool_manifest() -> dict:
    """Every class is read, so a missing member of any class refuses."""
    return {"verdict": {name: normalized_hash(BIN / name) for name in VERDICT_FILES},
            "gate": {name: file_hash(BIN / name) for name in GATE_FILES},
            "check": {name: file_hash(BIN / name) for name in CHECK_FILES}}


def tool_files() -> dict:
    """The tool entries a binding digest covers: the `verdict` class only."""
    return tool_manifest()["verdict"]


def policy_files(root: pathlib.Path) -> dict:
    files = {}
    for name in POLICY_FILES:
        path = sd_lib.local_block_path(root) if name == sd_lib.LOCAL_FILE_NAME else root / name
        # Preserve item-backed repository-policy I/O errors for existing callers.
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() or path.is_symlink() else "absent"
    files["external_review_policy"] = digest({"path": str(sd_lib.machine_config_path()), "value": sd_lib.core_setting("external_reviews")})
    return files


def binding_manifest(root: pathlib.Path) -> dict:
    """What a receipt stores beside its digest, so a moved binding can name what moved."""
    return {"schema": 2, "normalizer": NORMALIZER, **tool_manifest(), "policy": policy_files(root)}


def manifest_digest(manifest: dict) -> str:
    return digest({name: manifest[name] for name in ("schema", "normalizer", "verdict", "policy")})


def review_binding(root: pathlib.Path) -> str:
    return manifest_digest(binding_manifest(root))


def binding_change(stored: object, current: dict) -> list[tuple[str, str]]:
    """Each entry that differs, with its class. Gate and check entries are named, never decisive."""
    if not isinstance(stored, dict) or stored.get("schema") != current["schema"]:
        return [(LEGACY_ENTRY, "legacy")]
    if stored.get("normalizer") != current["normalizer"]:
        return [(f"normalizer changed from {stored.get('normalizer')} to {current['normalizer']}", "verdict")]
    changed = []
    for kind in ("verdict", "policy", "gate", "check"):
        before, after = stored.get(kind) or {}, current[kind]
        changed += [(name, kind) for name in sorted(set(before) | set(after)) if before.get(name) != after.get(name)]
    return changed


def describe_change(changed: list[tuple[str, str]], limit: int = 5) -> str:
    """`sd-review (verdict), ...; also changed, not binding: sd-ship (gate)`."""
    def listed(rows):
        text = ", ".join(f"{name} ({kind})" for name, kind in rows[:limit])
        return text + (f" and {len(rows) - limit} more" if len(rows) > limit else "")
    binding = [row for row in changed if row[1] not in ("gate", "check")]
    other = [row for row in changed if row[1] in ("gate", "check")]
    parts = [listed(binding)] if binding else []
    if other:
        parts.append("also changed, not binding: " + listed(other))
    return "; ".join(parts)


def adjudicator_binding(library_file: str) -> str:
    # Tool files by their `verdict` class only (sd:1834); the library, the
    # policy files and the skill references stay byte-exact.
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
