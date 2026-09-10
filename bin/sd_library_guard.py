"""Keep provisioning an older committed source from breaking a migrated store."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path


def schema_version(source: str) -> int | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Name)
                   and node.id == "SCHEMA_VERSION" and isinstance(node.ctx, ast.Store)]
    if len(assignments) != 1:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SCHEMA_VERSION" for target in node.targets
        ) and isinstance(node.value, ast.Constant) and type(node.value.value) is int and node.value.value > 0:
            return node.value.value
    return None


def downgrade_refusal(checkout: Path, system: Path, ref: str,
                      git_output: Callable[[list[str], Path], str | None]) -> str:
    packages = sorted((checkout / ".venv/lib").glob("python*/site-packages/sd_db"))
    if not packages:
        return ""
    installed = [package / "schema.py" for package in packages]
    candidate = schema_version(git_output(["show", f"{ref}:local-sd-db/sd_db/schema.py"], system) or "")
    try:
        versions = [schema_version(path.read_text(encoding="utf-8")) for path in installed]
    except (OSError, UnicodeError) as error:
        return f"preserving installed sd_db: cannot inspect its schema ({error})"
    if candidate is None or any(version is None for version in versions):
        return "preserving installed sd_db: cannot verify the candidate and installed schema versions"
    current = max(version for version in versions if version is not None)
    if candidate < current:
        return (f"preserving installed sd_db schema {current}: committed source {ref} has schema "
                f"{candidate}; publish the matching system changes before provisioning again")
    return ""
