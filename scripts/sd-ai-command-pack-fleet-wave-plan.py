#!/usr/bin/env python3
"""Plan bounded fleet starts and manifest-ordered merge consideration."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import sd_ai_command_pack_fleet_lib as fleet_lib

STATE_SCHEMA_VERSION = 1
PLAN_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 64 * 1024
OBSERVATION_STATES = frozenset(
    {
        "pending",
        "in-flight",
        "ready",
        "at-target",
        "merged",
        "pr-open",
        "skipped",
        "failed",
        "blocked",
    }
)
ACTIVE_STATES = frozenset({"in-flight", "ready"})
TERMINAL_STATES = frozenset(
    {"at-target", "merged", "pr-open", "skipped", "failed", "blocked"}
)
CANARY_SUCCESS_STATES = frozenset({"at-target", "merged"})


class FleetWavePlanError(ValueError):
    """Raised when policy or observed rollout state is unsafe to schedule."""


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        node = path.lstat()
    except FileNotFoundError:
        raise FleetWavePlanError(f"{label} is missing") from None
    except OSError:
        raise FleetWavePlanError(f"{label} cannot be inspected") from None
    if stat.S_ISLNK(node.st_mode) or not stat.S_ISREG(node.st_mode):
        raise FleetWavePlanError(f"{label} must be a regular file")
    if node.st_size > MAX_STATE_BYTES:
        raise FleetWavePlanError(f"{label} exceeds {MAX_STATE_BYTES} bytes")
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise FleetWavePlanError(f"{label} is not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise FleetWavePlanError(f"{label} must be a JSON object")
    return payload


def parse_observations(
    payload: Mapping[str, Any],
    consumers: Sequence[fleet_lib.FleetConsumer],
) -> dict[str, dict[str, Any]]:
    if set(payload) != {"schemaVersion", "consumers"}:
        raise FleetWavePlanError("wave state fields must be schemaVersion and consumers")
    if payload.get("schemaVersion") != STATE_SCHEMA_VERSION:
        raise FleetWavePlanError(
            f"wave state schemaVersion must be {STATE_SCHEMA_VERSION}"
        )
    rows = payload.get("consumers")
    if not isinstance(rows, list):
        raise FleetWavePlanError("wave state consumers must be an array")

    known = {consumer.name: consumer for consumer in consumers}
    observations: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        label = f"wave state consumers[{index}]"
        if not isinstance(row, dict) or set(row) != {
            "name",
            "state",
            "packBlocker",
        }:
            raise FleetWavePlanError(
                f"{label} fields must be name, state, and packBlocker"
            )
        name = row.get("name")
        state = row.get("state")
        pack_blocker = row.get("packBlocker")
        if not isinstance(name, str) or name not in known:
            raise FleetWavePlanError(f"{label} names an unknown consumer")
        if name in observations:
            raise FleetWavePlanError(f"wave state repeats consumer {name}")
        if not isinstance(state, str) or state not in OBSERVATION_STATES:
            raise FleetWavePlanError(f"{label} has invalid state")
        if not isinstance(pack_blocker, bool):
            raise FleetWavePlanError(f"{label} packBlocker must be boolean")
        observations[name] = {
            "state": state,
            "packBlocker": pack_blocker,
        }

    missing = [consumer.name for consumer in consumers if consumer.name not in observations]
    if missing:
        raise FleetWavePlanError(f"wave state is missing consumer {missing[0]}")
    return observations


def _result(
    *,
    cohort: fleet_lib.FleetRolloutCohort | None,
    can_start: Sequence[str] = (),
    merge_candidate: str | None = None,
    stop_starting: bool = False,
    hold_merges: bool = False,
    complete: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "cohort": cohort.name if cohort is not None else None,
        "strategy": cohort.strategy if cohort is not None else None,
        "maxConcurrency": cohort.max_concurrency if cohort is not None else 0,
        "canStart": list(can_start),
        "mergeCandidate": merge_candidate,
        "stopStarting": stop_starting,
        "holdMerges": hold_merges,
        "complete": complete,
        "reason": reason,
    }


def plan_rollout(
    policy: fleet_lib.FleetRolloutPolicy,
    observations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    blockers = [
        name for name, row in observations.items() if row.get("packBlocker") is True
    ]
    if blockers:
        return _result(
            cohort=None,
            stop_starting=True,
            hold_merges=True,
            reason=f"pack blocker reported by {blockers[0]}",
        )

    active_cohort: fleet_lib.FleetRolloutCohort | None = None
    for index, cohort in enumerate(policy.cohorts):
        states = [str(observations[name]["state"]) for name in cohort.consumers]
        if index == 0:
            failed_canaries = [
                name
                for name, state in zip(cohort.consumers, states, strict=True)
                if state in TERMINAL_STATES and state not in CANARY_SUCCESS_STATES
            ]
            if failed_canaries:
                return _result(
                    cohort=cohort,
                    stop_starting=True,
                    hold_merges=True,
                    reason=f"canary health is incomplete at {failed_canaries[0]}",
                )
            if all(state in CANARY_SUCCESS_STATES for state in states):
                continue
        elif all(state in TERMINAL_STATES for state in states):
            continue
        active_cohort = cohort
        break

    if active_cohort is None:
        return _result(cohort=None, complete=True)

    active_names = [
        name
        for name in active_cohort.consumers
        if observations[name]["state"] in ACTIVE_STATES
    ]
    if len(active_names) > active_cohort.max_concurrency:
        raise FleetWavePlanError(
            f"cohort {active_cohort.name} exceeds configured concurrency"
        )
    capacity = active_cohort.max_concurrency - len(active_names)
    can_start = [
        name
        for name in active_cohort.consumers
        if observations[name]["state"] == "pending"
    ][:capacity]

    merge_candidate: str | None = None
    for name in active_cohort.consumers:
        state = observations[name]["state"]
        if state in TERMINAL_STATES:
            continue
        if state == "ready":
            merge_candidate = name
        break

    reason: str | None = None
    if not can_start and merge_candidate is None:
        reason = "waiting for the active cohort to settle"
    return _result(
        cohort=active_cohort,
        can_start=can_start,
        merge_candidate=merge_candidate,
        reason=reason,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan bounded post-canary fleet work without mutating repositories."
    )
    parser.add_argument(
        "--fleet",
        type=Path,
        default=fleet_lib.DEFAULT_FLEET_MANIFEST,
        help="schema-versioned fleet manifest",
    )
    parser.add_argument("--state", type=Path, required=True, help="observed wave state")
    parser.add_argument("--json", action="store_true")
    return parser


def render_human(plan: Mapping[str, Any]) -> str:
    starts = ", ".join(plan["canStart"]) or "none"
    return "\n".join(
        (
            f"cohort: {plan['cohort'] or 'none'}",
            f"strategy: {plan['strategy'] or 'none'}",
            f"max concurrency: {plan['maxConcurrency']}",
            f"start: {starts}",
            f"merge candidate: {plan['mergeCandidate'] or 'none'}",
            f"stop starting: {'yes' if plan['stopStarting'] else 'no'}",
            f"hold merges: {'yes' if plan['holdMerges'] else 'no'}",
            f"complete: {'yes' if plan['complete'] else 'no'}",
            f"reason: {plan['reason'] or 'none'}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = _load_json_object(args.fleet, "fleet manifest")
        consumers = fleet_lib.parse_fleet_consumers(manifest)
        policy = fleet_lib.parse_fleet_rollout_policy(manifest, consumers)
        observations = parse_observations(
            _load_json_object(args.state, "wave state"),
            consumers,
        )
        plan = plan_rollout(policy, observations)
    except (FleetWavePlanError, fleet_lib.FleetConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(plan, sort_keys=True, separators=(",", ":")))
    else:
        print(render_human(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
