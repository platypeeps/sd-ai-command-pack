"""Read-only readiness; runtime permission and service health remain unknown."""

from __future__ import annotations

import os
import shutil
from typing import Any, Mapping, Sequence

import sd_registry


def blocker(code: str, boundary: str, action: str, provider: str | None = None) -> dict[str, Any]:
    return {"code": code, "boundary": boundary, "provider": provider, "next_action": action}


def select_ready_candidates(registry: sd_registry.Registry, name: str | None, *, explain: bool, **kwargs: Any) -> tuple[list[sd_registry.Provider], str]:
    try:
        return sd_registry.select_reviewers(registry, name, **kwargs), ""
    except sd_registry.RegistryError as error:
        if not explain:
            raise
        return [], str(error)


def review_readiness(result: Mapping[str, Any], chosen: Sequence[sd_registry.Provider], env: Mapping[str, str]) -> dict[str, Any]:
    blockers, warnings = [], []
    for key, code in (("registry_refusal", "registry_unavailable"), ("consent_refusal", "consent_missing"),
                      ("authorship_refusal", "authorship_unknown"), ("selection_refusal", "reviewer_unavailable")):
        if result.get(key) and result["requested_reviews"]:
            blockers.append(blocker(code, "policy", str(result[key])))
    runnable = 0
    material = result.get("input_manifest", {})
    for provider in chosen:
        issues = provider_issues(provider, result["codex_preflight"], env, result.get("repo", ""))
        if material.get("transport_bytes", {}).get(provider.name, 0) > material.get("limit_bytes", 0):
            issues.append(blocker("input_oversized", "input", "Split the branch using input_manifest; no review partition was executed.", provider.name))
        if issues:
            warnings.extend(issues)
        else:
            runnable += 1
    if runnable < result["requested_reviews"]:
        blockers.extend(warnings)
        if not warnings:
            blockers.append(blocker("reviewer_unavailable", "provider", "Select an independent, enabled, consented reviewer."))
        warnings = []
    if material.get("status") == "oversized" and not material.get("transport_bytes"):
        blockers.append(blocker("input_oversized", "input", "Split the branch using input_manifest; no review partition was executed."))
    if material.get("error"):
        blockers.append(blocker("input_unreadable", "input", str(material["error"])))
    return {"status": "blocked" if blockers else "ready", "blockers": blockers, "warnings": warnings,
            "runtime_approval": "not_observable"}


def provider_issues(provider: sd_registry.Provider, auth: Mapping[str, Any], env: Mapping[str, str], root: str) -> list[dict[str, Any]]:
    issues = []
    child = sd_registry.provider_environment(provider, env)
    refused = sd_registry.refuse_environment(provider, child)
    if refused:
        issues.append(blocker("environment_refused", "provider", refused, provider.name))
    if provider.url:
        missing = [name for name in provider.env if not child.get(name)]
        if missing:
            issues.append(blocker("authentication_missing", "authentication", "Provide declared credentials: " + ", ".join(missing), provider.name))
    else:
        executable = sd_registry.executable(provider.start or "")
        if executable and os.sep in executable and not os.path.isabs(executable):
            executable = os.path.join(root, executable)
        search_path = os.pathsep.join(os.path.join(root, component) for component in os.get_exec_path(child))
        if not executable or not shutil.which(executable, path=search_path):
            issues.append(blocker("executable_missing", "runtime", f"Install the configured executable for {provider.name}.", provider.name))
        if provider.reader == "codex-json" and not auth.get("ok"):
            issues.append(blocker("authentication_refused", "authentication", str(auth.get("reason")), provider.name))
    return issues
