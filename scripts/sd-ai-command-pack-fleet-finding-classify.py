#!/usr/bin/env python3
"""Classify verified fleet findings as release blockers or deferred follow-ups."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import cast

SCHEMA_VERSION = 1
MAX_FINDINGS = 200
MAX_SUMMARY_LENGTH = 500
MAX_EVIDENCE_LENGTH = 2000
MAX_RATIONALE_LENGTH = 1000
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")

BLOCK = "block-corrective-release"
DEFER = "defer-follow-up"
DISPOSITIONS = frozenset({BLOCK, DEFER})
BLOCKING_FAMILIES = frozenset(
    {"correctness", "security", "install-audit", "compatibility"}
)
DEFERRED_FAMILIES = frozenset(
    {
        "hardening",
        "style",
        "test-implementation",
        "documentation",
        "diagnostics",
        "consumer-unrelated",
    }
)
CONTRACT_FAMILIES = BLOCKING_FAMILIES | DEFERRED_FAMILIES
ROOT_FIELDS = frozenset({"schemaVersion", "findings"})
FINDING_FIELDS = frozenset(
    {
        "id",
        "contractFamily",
        "summary",
        "evidence",
        "reviewer",
        "path",
        "line",
        "impact",
        "impactEvidence",
        "overrideDisposition",
        "overrideRationale",
    }
)


class FleetFindingError(ValueError):
    """Raised when fleet finding input cannot be classified safely."""


@dataclass(frozen=True)
class Finding:
    id: str
    contract_family: str
    summary: str
    evidence: str
    reviewer: str
    path: str | None
    line: int | None
    impact: str
    impact_evidence: str | None
    override_disposition: str | None
    override_rationale: str | None

    @property
    def signature_parts(self) -> tuple[object, ...]:
        return (
            self.reviewer.casefold(),
            self.path,
            self.line,
            self.summary,
        )

    @property
    def policy_parts(self) -> tuple[object, ...]:
        return (
            self.contract_family,
            self.impact,
            self.impact_evidence,
            self.override_disposition,
            self.override_rationale,
        )

    @property
    def dedupe_key(self) -> str:
        encoded = json.dumps(
            self.signature_parts,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class OwnerDisposition:
    finding: Finding
    observation_ids: tuple[str, ...]
    default_disposition: str
    computed_disposition: str
    final_disposition: str
    rationale: str
    escalated: bool
    override_applied: bool

    def as_json(self) -> dict[str, object]:
        return {
            "ownerId": self.finding.id,
            "observationIds": list(self.observation_ids),
            "dedupeKey": self.finding.dedupe_key,
            "contractFamily": self.finding.contract_family,
            "summary": self.finding.summary,
            "evidence": self.finding.evidence,
            "defaultDisposition": self.default_disposition,
            "computedDisposition": self.computed_disposition,
            "finalDisposition": self.final_disposition,
            "rationale": self.rationale,
            "escalation": {
                "applied": self.escalated,
                "evidence": self.finding.impact_evidence,
            },
            "override": {
                "applied": self.override_applied,
                "disposition": self.finding.override_disposition,
                "rationale": self.finding.override_rationale,
            },
        }


@dataclass(frozen=True)
class Classification:
    owners: tuple[OwnerDisposition, ...]
    observations: tuple[dict[str, object], ...]

    @property
    def blockers(self) -> tuple[OwnerDisposition, ...]:
        return tuple(owner for owner in self.owners if owner.final_disposition == BLOCK)

    @property
    def deferred(self) -> tuple[OwnerDisposition, ...]:
        return tuple(owner for owner in self.owners if owner.final_disposition == DEFER)

    @property
    def exit_code(self) -> int:
        return 1 if self.blockers else 0

    @property
    def decision(self) -> str:
        return "pause-corrective-release" if self.blockers else "continue-with-follow-ups"

    def as_json(self) -> dict[str, object]:
        duplicate_count = len(self.observations) - len(self.owners)
        override_count = sum(owner.override_applied for owner in self.owners)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "decision": self.decision,
            "exitCode": self.exit_code,
            "counts": {
                "observations": len(self.observations),
                "owners": len(self.owners),
                "duplicates": duplicate_count,
                "blockers": len(self.blockers),
                "deferred": len(self.deferred),
                "overrides": override_count,
            },
            "blockers": [owner.as_json() for owner in self.blockers],
            "deferred": [owner.as_json() for owner in self.deferred],
            "owners": [owner.as_json() for owner in self.owners],
            "observations": list(self.observations),
        }


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FleetFindingError(f"{label} must be an object")
    return value


def _strict_fields(value: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise FleetFindingError(f"{label} has unknown field: {unknown[0]}")


def _text(value: object, label: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise FleetFindingError(f"{label} must be a string")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise FleetFindingError(f"{label} contains a control character")
    normalized = " ".join(value.split())
    if not normalized:
        raise FleetFindingError(f"{label} must not be empty")
    if len(normalized) > limit:
        raise FleetFindingError(f"{label} exceeds {limit} characters")
    return normalized


def _optional_text(value: object, label: str, *, limit: int) -> str | None:
    if value is None:
        return None
    return _text(value, label, limit=limit)


def _safe_repo_path(value: str) -> bool:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return not (
        not value
        or value == "."
        or value.startswith("-")
        or "\\" in value
        or posix.as_posix() != value
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
        or ".." in windows.parts
    )


def parse_finding(value: object, index: int) -> Finding:
    payload = _object(value, f"finding {index}")
    _strict_fields(payload, FINDING_FIELDS, f"finding {index}")

    finding_id = _text(payload.get("id"), f"finding {index} id", limit=80)
    if not ID_RE.fullmatch(finding_id) or finding_id.startswith("-"):
        raise FleetFindingError(f"finding {index} id is not a safe identifier")

    family = _text(
        payload.get("contractFamily"),
        f"finding {finding_id} contractFamily",
        limit=40,
    )
    if family not in CONTRACT_FAMILIES:
        raise FleetFindingError(
            f"finding {finding_id} contractFamily must be one of: "
            + ", ".join(sorted(CONTRACT_FAMILIES))
        )

    summary = _text(
        payload.get("summary"),
        f"finding {finding_id} summary",
        limit=MAX_SUMMARY_LENGTH,
    )
    evidence = _text(
        payload.get("evidence"),
        f"finding {finding_id} evidence",
        limit=MAX_EVIDENCE_LENGTH,
    )
    reviewer = _text(
        payload.get("reviewer"),
        f"finding {finding_id} reviewer",
        limit=100,
    )

    path = _optional_text(
        payload.get("path"),
        f"finding {finding_id} path",
        limit=500,
    )
    if path is not None and not _safe_repo_path(path):
        raise FleetFindingError(f"finding {finding_id} path is unsafe: {path!r}")

    raw_line = payload.get("line")
    if raw_line is not None and (
        isinstance(raw_line, bool) or not isinstance(raw_line, int) or raw_line < 1
    ):
        raise FleetFindingError(f"finding {finding_id} line must be a positive integer")
    line_value = cast(int | None, raw_line)

    raw_impact = payload.get("impact", "default")
    if not isinstance(raw_impact, str) or raw_impact not in {"default", "blocker"}:
        raise FleetFindingError(f"finding {finding_id} impact must be 'default' or 'blocker'")
    impact = raw_impact
    impact_evidence = _optional_text(
        payload.get("impactEvidence"),
        f"finding {finding_id} impactEvidence",
        limit=MAX_RATIONALE_LENGTH,
    )
    if impact == "blocker" and impact_evidence is None:
        raise FleetFindingError(
            f"finding {finding_id} blocker impact requires impactEvidence"
        )
    if impact == "default" and impact_evidence is not None:
        raise FleetFindingError(
            f"finding {finding_id} impactEvidence requires impact 'blocker'"
        )

    raw_override = payload.get("overrideDisposition")
    if raw_override is not None and (
        not isinstance(raw_override, str) or raw_override not in DISPOSITIONS
    ):
        raise FleetFindingError(
            f"finding {finding_id} overrideDisposition must be {BLOCK!r} or {DEFER!r}"
        )
    override = cast(str | None, raw_override)
    override_rationale = _optional_text(
        payload.get("overrideRationale"),
        f"finding {finding_id} overrideRationale",
        limit=MAX_RATIONALE_LENGTH,
    )
    if (override is None) != (override_rationale is None):
        raise FleetFindingError(
            f"finding {finding_id} overrideDisposition and overrideRationale must appear together"
        )

    return Finding(
        id=finding_id,
        contract_family=family,
        summary=summary,
        evidence=evidence,
        reviewer=reviewer,
        path=path,
        line=line_value,
        impact=impact,
        impact_evidence=impact_evidence,
        override_disposition=override,
        override_rationale=override_rationale,
    )


def parse_payload(value: object) -> tuple[Finding, ...]:
    payload = _object(value, "fleet finding input")
    _strict_fields(payload, ROOT_FIELDS, "fleet finding input")
    schema_version = payload.get("schemaVersion")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise FleetFindingError(
            f"fleet finding input schemaVersion must be {SCHEMA_VERSION}"
        )
    raw_findings = payload.get("findings")
    if not isinstance(raw_findings, list) or not raw_findings:
        raise FleetFindingError("fleet finding input findings must be a non-empty array")
    if len(raw_findings) > MAX_FINDINGS:
        raise FleetFindingError(
            f"fleet finding input exceeds the {MAX_FINDINGS}-finding limit"
        )
    findings = tuple(
        parse_finding(raw_finding, index)
        for index, raw_finding in enumerate(raw_findings, start=1)
    )
    ids = [finding.id for finding in findings]
    if len(ids) != len(set(ids)):
        raise FleetFindingError("fleet finding input contains duplicate finding ids")
    return findings


def _owner_disposition(
    finding: Finding,
    observation_ids: Sequence[str],
) -> OwnerDisposition:
    default = BLOCK if finding.contract_family in BLOCKING_FAMILIES else DEFER
    escalated = finding.impact == "blocker" and default == DEFER
    computed = BLOCK if finding.impact == "blocker" else default
    override_applied = finding.override_disposition is not None
    final = finding.override_disposition or computed
    if override_applied:
        rationale = f"operator override: {finding.override_rationale}"
    elif escalated:
        rationale = f"blocker impact evidence: {finding.impact_evidence}"
    elif default == BLOCK:
        rationale = (
            f"{finding.contract_family} is a released-pack blocker; evidence: "
            f"{finding.evidence}"
        )
    else:
        rationale = (
            f"{finding.contract_family} defaults to follow-up timing; evidence: "
            f"{finding.evidence}"
        )
    return OwnerDisposition(
        finding=finding,
        observation_ids=tuple(observation_ids),
        default_disposition=default,
        computed_disposition=computed,
        final_disposition=final,
        rationale=rationale,
        escalated=escalated,
        override_applied=override_applied,
    )


def classify_findings(findings: Sequence[Finding]) -> Classification:
    owners_by_signature: dict[tuple[object, ...], Finding] = {}
    observation_ids: dict[tuple[object, ...], list[str]] = {}
    observations: list[dict[str, object]] = []
    for finding in findings:
        signature = finding.signature_parts
        owner = owners_by_signature.get(signature)
        if owner is None:
            owner = finding
            owners_by_signature[signature] = owner
            observation_ids[signature] = []
        elif owner.policy_parts != finding.policy_parts:
            raise FleetFindingError(
                f"exact duplicate finding {finding.id} conflicts with owner {owner.id} policy"
            )
        observation_ids[signature].append(finding.id)
        observations.append(
            {
                "id": finding.id,
                "ownerId": owner.id,
                "duplicate": finding.id != owner.id,
                "dedupeKey": owner.dedupe_key,
                "evidence": finding.evidence,
            }
        )

    owners = tuple(
        _owner_disposition(owner, observation_ids[signature])
        for signature, owner in owners_by_signature.items()
    )
    dispositions = {owner.finding.id: owner for owner in owners}
    enriched_observations: list[dict[str, object]] = []
    for observation in observations:
        disposition = dispositions[cast(str, observation["ownerId"])]
        enriched_observations.append(
            {
                **observation,
                "defaultDisposition": disposition.default_disposition,
                "computedDisposition": disposition.computed_disposition,
                "finalDisposition": disposition.final_disposition,
                "rationale": disposition.rationale,
                "escalation": {
                    "applied": disposition.escalated,
                    "evidence": disposition.finding.impact_evidence,
                },
                "override": {
                    "applied": disposition.override_applied,
                    "disposition": disposition.finding.override_disposition,
                    "rationale": disposition.finding.override_rationale,
                },
            }
        )
    return Classification(owners=owners, observations=tuple(enriched_observations))


def classify_payload(value: object) -> Classification:
    return classify_findings(parse_payload(value))


def load_payload(path: Path) -> object:
    resolved = path.expanduser().resolve()
    if path.is_symlink() or not resolved.is_file():
        raise FleetFindingError(f"fleet finding input is not a regular file: {path}")
    try:
        return json.loads(resolved.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FleetFindingError(f"cannot read fleet finding input {path}: {exc}") from exc


def render_human(result: Classification) -> str:
    duplicate_count = len(result.observations) - len(result.owners)
    override_count = sum(owner.override_applied for owner in result.owners)
    lines = [
        f"fleet finding decision: {result.decision}",
        (
            "owners: "
            f"{len(result.owners)}; blockers: {len(result.blockers)}; "
            f"deferred: {len(result.deferred)}; duplicates: {duplicate_count}; "
            f"overrides: {override_count}"
        ),
    ]
    for owner in result.owners:
        lines.append(
            f"- {owner.finding.id} · {owner.finding.contract_family} · "
            f"{owner.final_disposition} · {owner.rationale}"
        )
        duplicates = owner.observation_ids[1:]
        if duplicates:
            lines.append("  duplicates: " + ", ".join(duplicates))
    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify verified fleet findings for rollout interruption timing."
    )
    parser.add_argument("--input", required=True, type=Path, help="schema-versioned finding JSON")
    parser.add_argument("--json", action="store_true", help="print deterministic JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = classify_payload(load_payload(args.input))
    except FleetFindingError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        "decision": "invalid-pause",
                        "exitCode": 2,
                        "error": str(exc),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"fleet finding classification error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.as_json(), indent=2, sort_keys=True))
    else:
        print(render_human(result))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
