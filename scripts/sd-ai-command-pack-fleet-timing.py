#!/usr/bin/env python3
"""Record local, resumable timing evidence for source-owned fleet rollouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1024 * 1024
MAX_REASON_LENGTH = 500
LOCK_WAIT_SECONDS = 5.0
STALE_LOCK_SECONDS = 60.0

SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")
SECRET_RE = re.compile(
    r"(?i)(?:gh[pousr]_|github_pat_|xox[baprs]-|sk-[A-Za-z0-9]"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|(?:token|password|secret|api[_-]?key)\s*[:=]\s*\S+)"
)
ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9/])(?:~[/\\]|/[A-Za-z0-9._~-]|[A-Za-z]:[/\\]|\\\\\S+)"
)
REMOTE_URL_RE = re.compile(
    r"(?i)(?:\b[a-z][a-z0-9+.-]*://\S+|\b[a-z0-9._-]+@[a-z0-9.-]+:\S+)"
)
QUOTED_OUTPUT_PATH_RE = re.compile(
    r"(?P<quote>['\"])(?:~[/\\]|/[A-Za-z0-9._~-]|[A-Za-z]:[/\\]|\\\\)"
    r"[^'\"]*(?P=quote)"
)
UNQUOTED_OUTPUT_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:~[/\\]|/[A-Za-z0-9._~-]|[A-Za-z]:[/\\]|\\\\)"
    r"[^\s'\"<>]*"
)

STAGES = (
    "preflight",
    "checkout-validation",
    "install",
    "audit",
    "local-gate",
    "commit-push",
    "pr-creation",
    "reviewer-wait",
    "ci-wait",
    "housekeeping",
    "post-merge-audit",
)
STAGE_ORDER = {name: index for index, name in enumerate(STAGES)}
STAGE_OUTCOMES = frozenset({"passed", "failed", "skipped", "interrupted"})
STAGE_REASON_REQUIRED = frozenset({"failed", "skipped", "interrupted"})
CONSUMER_OUTCOMES = frozenset(
    {"at-target", "refreshed-merged", "pr-open", "skipped", "failed", "blocked"}
)
CONSUMER_REASON_REQUIRED = frozenset({"skipped", "failed", "blocked"})
CONSUMER_REASON_FORBIDDEN = frozenset({"at-target", "refreshed-merged"})

ROOT_FIELDS = frozenset(
    {
        "schemaVersion",
        "runId",
        "repositoryDigest",
        "targetVersion",
        "status",
        "createdAtWallNs",
        "updatedAtWallNs",
        "completedAtWallNs",
        "fleetStages",
        "consumers",
    }
)
CONSUMER_FIELDS = frozenset({"name", "priority", "outcome", "reason", "stages"})
STAGE_FIELDS = frozenset({"name", "attempts"})
ATTEMPT_FIELDS = frozenset(
    {
        "attempt",
        "startedWallNs",
        "startedMonotonicNs",
        "endedWallNs",
        "elapsedNs",
        "outcome",
        "reason",
    }
)
LOCK_FIELDS = frozenset(
    {"schemaVersion", "runId", "repositoryDigest", "pid", "hostname", "acquiredAtWallNs"}
)


class FleetTimingError(ValueError):
    """Raised when timing state or an operation is unsafe."""


@dataclass(frozen=True)
class ClockReading:
    wall_ns: int
    monotonic_ns: int


def system_reading() -> ClockReading:
    clock_gettime_ns = getattr(time, "clock_gettime_ns", None)
    clock_monotonic = getattr(time, "CLOCK_MONOTONIC", None)
    if callable(clock_gettime_ns) and isinstance(clock_monotonic, int):
        try:
            monotonic_ns = clock_gettime_ns(clock_monotonic)
        except (OSError, ValueError):
            monotonic_ns = time.monotonic_ns()
    else:
        monotonic_ns = time.monotonic_ns()
    return ClockReading(wall_ns=time.time_ns(), monotonic_ns=monotonic_ns)


def _strict_fields(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted((key for key in value if key not in allowed), key=str)
    missing = sorted(allowed - set(value))
    if unknown:
        raise FleetTimingError(f"{label} has unknown field: {unknown[0]}")
    if missing:
        raise FleetTimingError(f"{label} is missing field: {missing[0]}")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetTimingError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise FleetTimingError(f"{label} must be an array")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FleetTimingError(f"{label} must be an integer >= {minimum}")
    return value


def safe_token(value: object, label: str) -> str:
    if not isinstance(value, str) or not SAFE_TOKEN_RE.fullmatch(value):
        raise FleetTimingError(f"{label} must be a safe identifier")
    return value


def safe_reason(value: object, label: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise FleetTimingError(f"{label} is required")
        return None
    if not isinstance(value, str):
        raise FleetTimingError(f"{label} must be a string")
    if any(ord(character) < 32 for character in value):
        raise FleetTimingError(f"{label} contains a control character")
    normalized = " ".join(value.split())
    if not normalized:
        raise FleetTimingError(f"{label} must not be empty")
    if len(normalized) > MAX_REASON_LENGTH:
        raise FleetTimingError(f"{label} exceeds {MAX_REASON_LENGTH} characters")
    if SECRET_RE.search(normalized):
        raise FleetTimingError(f"{label} contains secret-like material")
    if REMOTE_URL_RE.search(normalized):
        raise FleetTimingError(f"{label} contains a remote URL")
    if ABSOLUTE_PATH_RE.search(normalized):
        raise FleetTimingError(f"{label} contains an absolute or home-relative path")
    return normalized


def public_error(value: BaseException) -> str:
    """Remove local path material before an error crosses the CLI boundary."""
    redacted = QUOTED_OUTPUT_PATH_RE.sub("<path>", str(value))
    redacted = UNQUOTED_OUTPUT_PATH_RE.sub("<path>", redacted)
    return " ".join(redacted.split())


def _optional_outcome(value: object, allowed: frozenset[str], label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        raise FleetTimingError(f"{label} is invalid")
    return value


def _json_payload(value: Mapping[str, Any]) -> str:
    try:
        payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    except (TypeError, ValueError) as exc:
        raise FleetTimingError(f"timing state is not JSON serializable: {exc}") from exc
    if len(payload.encode("utf-8")) > MAX_STATE_BYTES:
        raise FleetTimingError(f"timing state exceeds {MAX_STATE_BYTES} bytes")
    return payload


def validate_attempt(value: object, label: str) -> None:
    attempt = _object(value, label)
    _strict_fields(attempt, ATTEMPT_FIELDS, label)
    _integer(attempt["attempt"], f"{label} attempt", minimum=1)
    _integer(attempt["startedWallNs"], f"{label} startedWallNs")
    _integer(attempt["startedMonotonicNs"], f"{label} startedMonotonicNs")
    ended = attempt["endedWallNs"]
    elapsed = attempt["elapsedNs"]
    outcome = _optional_outcome(attempt["outcome"], STAGE_OUTCOMES, f"{label} outcome")
    reason = safe_reason(attempt["reason"], f"{label} reason")
    active_fields = (ended is None, elapsed is None, outcome is None)
    if len(set(active_fields)) != 1:
        raise FleetTimingError(f"{label} end fields must be all null or all populated")
    if ended is None:
        if reason is not None:
            raise FleetTimingError(f"{label} active attempt cannot have a reason")
        return
    _integer(ended, f"{label} endedWallNs")
    _integer(elapsed, f"{label} elapsedNs")
    assert outcome is not None
    if (outcome in STAGE_REASON_REQUIRED) != (reason is not None):
        requirement = "requires" if outcome in STAGE_REASON_REQUIRED else "forbids"
        raise FleetTimingError(f"{label} outcome {outcome} {requirement} a reason")


def validate_stage(value: object, label: str, *, fleet_scope: bool) -> None:
    stage = _object(value, label)
    _strict_fields(stage, STAGE_FIELDS, label)
    name = safe_token(stage["name"], f"{label} name")
    if name not in STAGES:
        raise FleetTimingError(f"{label} name is not a supported stage")
    if fleet_scope != (name == "preflight"):
        scope = "fleet" if fleet_scope else "consumer"
        raise FleetTimingError(f"{label} stage {name} is invalid for {scope} scope")
    attempts = _array(stage["attempts"], f"{label} attempts")
    if not attempts:
        raise FleetTimingError(f"{label} attempts must be non-empty")
    active_count = 0
    for index, attempt in enumerate(attempts, start=1):
        attempt_label = f"{label} attempt {index}"
        validate_attempt(attempt, attempt_label)
        attempt_object = _object(attempt, attempt_label)
        if attempt_object["attempt"] != index:
            raise FleetTimingError(f"{attempt_label} number is not sequential")
        active_count += attempt_object["endedWallNs"] is None
    if active_count > 1 or (active_count and attempts[-1]["endedWallNs"] is not None):
        raise FleetTimingError(f"{label} active attempt must be last and unique")


def validate_consumer(value: object, label: str) -> None:
    consumer = _object(value, label)
    _strict_fields(consumer, CONSUMER_FIELDS, label)
    safe_token(consumer["name"], f"{label} name")
    _integer(consumer["priority"], f"{label} priority")
    outcome = _optional_outcome(
        consumer["outcome"], CONSUMER_OUTCOMES, f"{label} outcome"
    )
    reason = safe_reason(consumer["reason"], f"{label} reason")
    if outcome is None and reason is not None:
        raise FleetTimingError(f"{label} active consumer cannot have a reason")
    if outcome in CONSUMER_REASON_REQUIRED and reason is None:
        raise FleetTimingError(f"{label} outcome {outcome} requires a reason")
    if outcome in CONSUMER_REASON_FORBIDDEN and reason is not None:
        raise FleetTimingError(f"{label} outcome {outcome} forbids a reason")
    stages = _array(consumer["stages"], f"{label} stages")
    names: list[str] = []
    for index, stage in enumerate(stages, start=1):
        stage_label = f"{label} stage {index}"
        validate_stage(stage, stage_label, fleet_scope=False)
        names.append(_object(stage, stage_label)["name"])
    if len(names) != len(set(names)):
        raise FleetTimingError(f"{label} contains duplicate stages")
    if outcome is not None and any(
        attempt["endedWallNs"] is None
        for stage in stages
        for attempt in stage["attempts"]
    ):
        raise FleetTimingError(f"{label} completed consumer has an active attempt")


def validate_state(value: object) -> dict[str, Any]:
    state = _object(value, "timing state")
    _strict_fields(state, ROOT_FIELDS, "timing state")
    schema = state["schemaVersion"]
    if isinstance(schema, bool) or schema != SCHEMA_VERSION:
        raise FleetTimingError(f"timing state schemaVersion must be {SCHEMA_VERSION}")
    safe_token(state["runId"], "timing state runId")
    digest = state["repositoryDigest"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise FleetTimingError("timing state repositoryDigest is malformed")
    safe_token(state["targetVersion"], "timing state targetVersion")
    if state["status"] not in {"active", "completed"}:
        raise FleetTimingError("timing state status is invalid")
    _integer(state["createdAtWallNs"], "timing state createdAtWallNs")
    _integer(state["updatedAtWallNs"], "timing state updatedAtWallNs")
    completed_at = state["completedAtWallNs"]
    if completed_at is not None:
        _integer(completed_at, "timing state completedAtWallNs")
    if (state["status"] == "completed") != (completed_at is not None):
        raise FleetTimingError("timing state completion fields disagree")

    fleet_stages = _array(state["fleetStages"], "timing state fleetStages")
    fleet_names: list[str] = []
    for index, stage in enumerate(fleet_stages, start=1):
        label = f"timing state fleet stage {index}"
        validate_stage(stage, label, fleet_scope=True)
        fleet_names.append(_object(stage, label)["name"])
    if len(fleet_names) != len(set(fleet_names)):
        raise FleetTimingError("timing state contains duplicate fleet stages")

    consumers = _array(state["consumers"], "timing state consumers")
    if not consumers:
        raise FleetTimingError("timing state consumers must be non-empty")
    identities: list[tuple[int, str]] = []
    for index, consumer in enumerate(consumers, start=1):
        label = f"timing state consumer {index}"
        validate_consumer(consumer, label)
        consumer_object = _object(consumer, label)
        identities.append((consumer_object["priority"], consumer_object["name"]))
    if len({name for _priority, name in identities}) != len(identities):
        raise FleetTimingError("timing state contains duplicate consumer names")
    if len({priority for priority, _name in identities}) != len(identities):
        raise FleetTimingError("timing state contains duplicate consumer priorities")
    if identities != sorted(identities):
        raise FleetTimingError("timing state consumers are not in rollout priority order")

    active_attempts = [
        attempt
        for stage in fleet_stages
        for attempt in stage["attempts"]
        if attempt["endedWallNs"] is None
    ] + [
        attempt
        for consumer in consumers
        for stage in consumer["stages"]
        for attempt in stage["attempts"]
        if attempt["endedWallNs"] is None
    ]
    if state["status"] == "completed":
        if active_attempts:
            raise FleetTimingError("completed timing state has active attempts")
        if any(consumer["outcome"] is None for consumer in consumers):
            raise FleetTimingError("completed timing state has active consumers")
    _json_payload(state)
    return state


def resolve_repository(path: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FleetTimingError(f"cannot resolve repository directory: {exc}") from exc
    if not resolved.is_dir():
        raise FleetTimingError("repository must be a directory")
    return resolved


def repository_digest(repo: Path) -> str:
    normalized = os.path.normcase(str(resolve_repository(repo)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def resolve_state_root(state_home: Path | None = None) -> Path:
    if state_home is not None:
        candidate = state_home.expanduser()
        if not candidate.is_absolute():
            raise FleetTimingError("state home must be an absolute path")
        return candidate
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        candidate = Path(xdg).expanduser()
        if candidate.is_absolute():
            return candidate / "sd-ai-command-pack"
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data and PureWindowsPath(local_app_data).is_absolute():
            return Path(local_app_data) / "sd-ai-command-pack" / "state"
    home = Path.home().expanduser()
    if not home.is_absolute():
        raise FleetTimingError("home directory must resolve to an absolute path")
    return home / ".local" / "state" / "sd-ai-command-pack"


def ensure_private_directory(path: Path) -> None:
    if path.is_symlink():
        raise FleetTimingError("timing state directory must not be a symlink")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise FleetTimingError(f"cannot create timing state directory: {exc}") from exc
    if path.is_symlink() or not path.is_dir():
        raise FleetTimingError("timing state directory is unusable")
    try:
        path.chmod(0o700)
    except OSError:
        pass


@dataclass(frozen=True)
class TimingStore:
    state_path: Path
    lock_path: Path
    repository_digest: str


def timing_store(repo: Path, run_id: str, state_home: Path | None = None) -> TimingStore:
    safe_token(run_id, "run ID")
    digest = repository_digest(repo)
    state_root = resolve_state_root(state_home)
    if state_root.is_symlink():
        raise FleetTimingError("timing state directory must not be a symlink")
    directory = state_root / "fleet-timing" / digest
    return TimingStore(
        state_path=directory / f"{run_id}.json",
        lock_path=directory / f"{run_id}.lock",
        repository_digest=digest,
    )


def read_json_file(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise FleetTimingError(f"{label} must not be a symlink")
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except FileNotFoundError:
        raise FleetTimingError(f"{label} does not exist") from None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FleetTimingError(f"cannot read {label}: {exc}") from exc
    return _object(value, label)


def load_state(store: TimingStore, run_id: str) -> dict[str, Any]:
    state = validate_state(read_json_file(store.state_path, "timing state"))
    if state["runId"] != run_id:
        raise FleetTimingError("timing state belongs to a different run")
    if state["repositoryDigest"] != store.repository_digest:
        raise FleetTimingError("timing state belongs to a different repository")
    return state


def atomic_write_state(store: TimingStore, state: Mapping[str, Any]) -> None:
    validate_state(state)
    ensure_private_directory(store.state_path.parent)
    if store.state_path.is_symlink():
        raise FleetTimingError("timing state must not be a symlink")
    payload = _json_payload(state)
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{store.state_path.name}.",
            suffix=".tmp",
            dir=store.state_path.parent,
        )
    except OSError as exc:
        raise FleetTimingError(f"cannot create temporary timing state: {exc}") from exc
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", errors="strict") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, store.state_path)
        try:
            store.state_path.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise FleetTimingError(f"cannot write timing state: {exc}") from exc


def process_alive(pid: object) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def _validate_lock(value: object, store: TimingStore, run_id: str) -> dict[str, Any]:
    lock = _object(value, "timing lock")
    _strict_fields(lock, LOCK_FIELDS, "timing lock")
    schema = _integer(lock["schemaVersion"], "timing lock schemaVersion")
    if schema != SCHEMA_VERSION:
        raise FleetTimingError("timing lock schema is malformed")
    if lock["runId"] != run_id or lock["repositoryDigest"] != store.repository_digest:
        raise FleetTimingError("timing lock belongs to another run or repository")
    _integer(lock["pid"], "timing lock pid", minimum=1)
    safe_reason(lock["hostname"], "timing lock hostname", required=True)
    _integer(lock["acquiredAtWallNs"], "timing lock acquiredAtWallNs")
    return lock


@contextmanager
def operation_lock(
    store: TimingStore,
    run_id: str,
    *,
    reading_fn: Callable[[], ClockReading] = system_reading,
    wait_seconds: float = LOCK_WAIT_SECONDS,
) -> Iterator[None]:
    ensure_private_directory(store.lock_path.parent)
    deadline = time.monotonic() + wait_seconds
    while True:
        if store.lock_path.is_symlink():
            raise FleetTimingError("timing lock must not be a symlink")
        reading = reading_fn()
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "runId": run_id,
            "repositoryDigest": store.repository_digest,
            "pid": os.getpid(),
            "hostname": socket.gethostname() or "unknown-host",
            "acquiredAtWallNs": reading.wall_ns,
        }
        try:
            descriptor = os.open(
                store.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            try:
                lock = _validate_lock(
                    read_json_file(store.lock_path, "timing lock"), store, run_id
                )
            except FleetTimingError:
                if not store.lock_path.exists():
                    continue
                if time.monotonic() >= deadline:
                    raise FleetTimingError(
                        "timing state is busy; retry the same operation"
                    ) from None
                time.sleep(0.05)
                continue
            age_ns = max(0, reading.wall_ns - lock["acquiredAtWallNs"])
            stale = age_ns > int(STALE_LOCK_SECONDS * 1_000_000_000)
            if stale and not process_alive(lock["pid"]):
                try:
                    store.lock_path.unlink()
                except OSError as exc:
                    raise FleetTimingError(f"cannot recover stale timing lock: {exc}") from exc
                continue
            if time.monotonic() >= deadline:
                raise FleetTimingError(
                    "timing state is busy; retry the same operation"
                ) from None
            time.sleep(0.05)
            continue
        except OSError as exc:
            raise FleetTimingError(f"cannot acquire timing lock: {exc}") from exc
        try:
            with os.fdopen(
                descriptor, "w", encoding="utf-8", errors="strict"
            ) as stream:
                stream.write(_json_payload(payload))
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            try:
                store.lock_path.unlink()
            except OSError:
                pass
            raise FleetTimingError(f"cannot write timing lock: {exc}") from exc
        break
    try:
        yield
    finally:
        try:
            store.lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise FleetTimingError(f"cannot release timing lock: {exc}") from exc


def parse_consumer(value: str) -> tuple[str, int]:
    if ":" not in value:
        raise FleetTimingError("consumer must use NAME:PRIORITY")
    name, raw_priority = value.rsplit(":", 1)
    safe_token(name, "consumer name")
    try:
        priority = int(raw_priority)
    except ValueError:
        raise FleetTimingError("consumer priority must be an integer") from None
    _integer(priority, "consumer priority")
    return name, priority


def new_state(
    run_id: str,
    target_version: str,
    repository_digest_value: str,
    consumers: Sequence[tuple[str, int]],
    reading: ClockReading,
) -> dict[str, Any]:
    safe_token(run_id, "run ID")
    safe_token(target_version, "target version")
    if not consumers:
        raise FleetTimingError("at least one consumer is required")
    normalized = sorted(consumers, key=lambda item: (item[1], item[0]))
    if len({name for name, _priority in normalized}) != len(normalized):
        raise FleetTimingError("consumer names must be unique")
    if len({priority for _name, priority in normalized}) != len(normalized):
        raise FleetTimingError("consumer priorities must be unique")
    state: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "repositoryDigest": repository_digest_value,
        "targetVersion": target_version,
        "status": "active",
        "createdAtWallNs": reading.wall_ns,
        "updatedAtWallNs": reading.wall_ns,
        "completedAtWallNs": None,
        "fleetStages": [],
        "consumers": [
            {
                "name": name,
                "priority": priority,
                "outcome": None,
                "reason": None,
                "stages": [],
            }
            for name, priority in normalized
        ],
    }
    return validate_state(state)


def initialize_store(
    store: TimingStore,
    run_id: str,
    target_version: str,
    consumers: Sequence[tuple[str, int]],
    reading: ClockReading,
) -> tuple[dict[str, Any], bool]:
    with operation_lock(store, run_id):
        if store.state_path.exists() or store.state_path.is_symlink():
            state = load_state(store, run_id)
            expected = sorted(consumers, key=lambda item: (item[1], item[0]))
            observed = [
                (consumer["name"], consumer["priority"])
                for consumer in state["consumers"]
            ]
            if state["targetVersion"] != target_version or observed != expected:
                raise FleetTimingError(
                    "existing timing run identity does not match target or consumers"
                )
            return state, False
        state = new_state(
            run_id, target_version, store.repository_digest, consumers, reading
        )
        atomic_write_state(store, state)
        return state, True


def _consumer(state: Mapping[str, Any], name: str) -> dict[str, Any]:
    for consumer in state["consumers"]:
        if consumer["name"] == name:
            return consumer
    raise FleetTimingError(f"unknown timing consumer: {name}")


def _stage_list(
    state: dict[str, Any], *, consumer_name: str | None, stage_name: str
) -> list[dict[str, Any]]:
    if stage_name not in STAGES:
        raise FleetTimingError(f"unsupported timing stage: {stage_name}")
    if consumer_name is None:
        if stage_name != "preflight":
            raise FleetTimingError("fleet scope accepts only preflight")
        return state["fleetStages"]
    if stage_name == "preflight":
        raise FleetTimingError("preflight is fleet-scoped")
    consumer = _consumer(state, consumer_name)
    if consumer["outcome"] is not None:
        raise FleetTimingError(f"consumer {consumer_name} already has a final outcome")
    return consumer["stages"]


def _find_stage(stages: Sequence[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((stage for stage in stages if stage["name"] == name), None)


def start_stage(
    state: dict[str, Any],
    *,
    consumer_name: str | None,
    stage_name: str,
    reading: ClockReading,
) -> bool:
    if state["status"] != "active":
        raise FleetTimingError("completed timing run cannot start a stage")
    stages = _stage_list(state, consumer_name=consumer_name, stage_name=stage_name)
    stage = _find_stage(stages, stage_name)
    if stage is None:
        stage = {"name": stage_name, "attempts": []}
        stages.append(stage)
        stages.sort(key=lambda item: STAGE_ORDER[item["name"]])
    attempts = stage["attempts"]
    if attempts and attempts[-1]["endedWallNs"] is None:
        return False
    attempts.append(
        {
            "attempt": len(attempts) + 1,
            "startedWallNs": reading.wall_ns,
            "startedMonotonicNs": reading.monotonic_ns,
            "endedWallNs": None,
            "elapsedNs": None,
            "outcome": None,
            "reason": None,
        }
    )
    return True


def end_stage(
    state: dict[str, Any],
    *,
    consumer_name: str | None,
    stage_name: str,
    outcome: str,
    reason: str | None,
    reading: ClockReading,
) -> bool:
    if outcome not in STAGE_OUTCOMES:
        raise FleetTimingError("stage outcome is invalid")
    normalized_reason = safe_reason(
        reason,
        "stage reason",
        required=outcome in STAGE_REASON_REQUIRED,
    )
    if outcome == "passed" and normalized_reason is not None:
        raise FleetTimingError("passed stage forbids a reason")
    stages = _stage_list(state, consumer_name=consumer_name, stage_name=stage_name)
    stage = _find_stage(stages, stage_name)
    if stage is None or not stage["attempts"]:
        raise FleetTimingError("stage has no attempt to end")
    attempt = stage["attempts"][-1]
    if attempt["endedWallNs"] is not None:
        if attempt["outcome"] == outcome and attempt["reason"] == normalized_reason:
            return False
        raise FleetTimingError("stage has no active attempt to end")
    elapsed = reading.monotonic_ns - attempt["startedMonotonicNs"]
    if elapsed < 0:
        raise FleetTimingError("monotonic clock moved backwards during stage")
    attempt.update(
        {
            "endedWallNs": reading.wall_ns,
            "elapsedNs": elapsed,
            "outcome": outcome,
            "reason": normalized_reason,
        }
    )
    return True


def end_consumer(
    state: dict[str, Any], *, name: str, outcome: str, reason: str | None
) -> bool:
    if state["status"] != "active":
        raise FleetTimingError("completed timing run cannot change a consumer")
    if outcome not in CONSUMER_OUTCOMES:
        raise FleetTimingError("consumer outcome is invalid")
    normalized_reason = safe_reason(
        reason,
        "consumer reason",
        required=outcome in CONSUMER_REASON_REQUIRED,
    )
    if outcome in CONSUMER_REASON_FORBIDDEN and normalized_reason is not None:
        raise FleetTimingError(f"consumer outcome {outcome} forbids a reason")
    consumer = _consumer(state, name)
    if any(
        attempt["endedWallNs"] is None
        for stage in consumer["stages"]
        for attempt in stage["attempts"]
    ):
        raise FleetTimingError(f"consumer {name} still has an active stage")
    if consumer["outcome"] is not None:
        if consumer["outcome"] == outcome and consumer["reason"] == normalized_reason:
            return False
        raise FleetTimingError(f"consumer {name} already has a different outcome")
    consumer["outcome"] = outcome
    consumer["reason"] = normalized_reason
    return True


def complete_state(state: dict[str, Any], reading: ClockReading) -> bool:
    if state["status"] == "completed":
        return False
    if any(
        attempt["endedWallNs"] is None
        for stage in state["fleetStages"]
        for attempt in stage["attempts"]
    ) or any(
        attempt["endedWallNs"] is None
        for consumer in state["consumers"]
        for stage in consumer["stages"]
        for attempt in stage["attempts"]
    ):
        raise FleetTimingError("cannot complete timing run with active stages")
    incomplete = [
        consumer["name"]
        for consumer in state["consumers"]
        if consumer["outcome"] is None
    ]
    if incomplete:
        raise FleetTimingError(
            "cannot complete timing run without consumer outcomes: "
            + ", ".join(incomplete)
        )
    state["status"] = "completed"
    state["completedAtWallNs"] = reading.wall_ns
    return True


def mutate_state(
    store: TimingStore,
    run_id: str,
    reading: ClockReading,
    mutation: Callable[[dict[str, Any]], bool],
) -> tuple[dict[str, Any], bool]:
    with operation_lock(store, run_id):
        state = load_state(store, run_id)
        changed = mutation(state)
        if changed:
            state["updatedAtWallNs"] = reading.wall_ns
            validate_state(state)
            atomic_write_state(store, state)
        return state, changed


def _attempt_interval(
    attempt: Mapping[str, Any], reading: ClockReading
) -> tuple[int, int, int]:
    if attempt["endedWallNs"] is None:
        elapsed = reading.monotonic_ns - attempt["startedMonotonicNs"]
        if elapsed < 0:
            raise FleetTimingError("monotonic clock moved backwards during active stage")
        end_wall = reading.wall_ns
    else:
        elapsed = attempt["elapsedNs"]
        end_wall = attempt["endedWallNs"]
    return attempt["startedWallNs"], max(attempt["startedWallNs"], end_wall), elapsed


def _merge_intervals(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _union_duration(intervals: Sequence[tuple[int, int]]) -> int:
    return sum(end - start for start, end in _merge_intervals(intervals))


def _intersection_duration(
    left: Sequence[tuple[int, int]], right: Sequence[tuple[int, int]]
) -> int:
    left_merged = _merge_intervals(left)
    right_merged = _merge_intervals(right)
    left_index = right_index = 0
    total = 0
    while left_index < len(left_merged) and right_index < len(right_merged):
        left_start, left_end = left_merged[left_index]
        right_start, right_end = right_merged[right_index]
        total += max(0, min(left_end, right_end) - max(left_start, right_start))
        if left_end <= right_end:
            left_index += 1
        else:
            right_index += 1
    return total


def _stage_summary(
    stages: Sequence[Mapping[str, Any]], reading: ClockReading
) -> tuple[list[dict[str, Any]], list[tuple[int, int]], int, int, dict[str, int]]:
    summaries: list[dict[str, Any]] = []
    all_intervals: list[tuple[int, int]] = []
    summed_elapsed = 0
    retries = 0
    totals: dict[str, int] = {}
    for stage in sorted(stages, key=lambda item: STAGE_ORDER[item["name"]]):
        elapsed = 0
        intervals: list[tuple[int, int]] = []
        active = False
        for attempt in stage["attempts"]:
            start, end, duration = _attempt_interval(attempt, reading)
            intervals.append((start, end))
            elapsed += duration
            active = active or attempt["endedWallNs"] is None
        retries += max(0, len(stage["attempts"]) - 1)
        summed_elapsed += elapsed
        all_intervals.extend(intervals)
        totals[stage["name"]] = totals.get(stage["name"], 0) + elapsed
        summaries.append(
            {
                "name": stage["name"],
                "attempts": len(stage["attempts"]),
                "active": active,
                "elapsedNs": elapsed,
                "activeWallNs": _union_duration(intervals),
            }
        )
    return summaries, all_intervals, summed_elapsed, retries, totals


def build_summary(state: Mapping[str, Any], reading: ClockReading) -> dict[str, Any]:
    validate_state(state)
    fleet_stage_summaries, fleet_intervals, fleet_elapsed, fleet_retries, totals = (
        _stage_summary(state["fleetStages"], reading)
    )
    consumer_summaries: list[dict[str, Any]] = []
    all_intervals = list(fleet_intervals)
    summed_elapsed = fleet_elapsed
    retry_count = fleet_retries
    all_reviewer_intervals: list[tuple[int, int]] = []
    all_ci_intervals: list[tuple[int, int]] = []
    for consumer in state["consumers"]:
        stage_summaries, intervals, elapsed, retries, consumer_totals = _stage_summary(
            consumer["stages"], reading
        )
        all_intervals.extend(intervals)
        summed_elapsed += elapsed
        retry_count += retries
        for name, duration in consumer_totals.items():
            totals[name] = totals.get(name, 0) + duration
        reviewer_intervals: list[tuple[int, int]] = []
        ci_intervals: list[tuple[int, int]] = []
        for stage in consumer["stages"]:
            target = (
                reviewer_intervals
                if stage["name"] == "reviewer-wait"
                else ci_intervals
                if stage["name"] == "ci-wait"
                else None
            )
            if target is not None:
                target.extend(
                    _attempt_interval(attempt, reading)[:2]
                    for attempt in stage["attempts"]
                )
        overlap = _intersection_duration(reviewer_intervals, ci_intervals)
        all_reviewer_intervals.extend(reviewer_intervals)
        all_ci_intervals.extend(ci_intervals)
        critical_path = (
            max(end for _start, end in intervals)
            - min(start for start, _end in intervals)
            if intervals
            else 0
        )
        consumer_summaries.append(
            {
                "name": consumer["name"],
                "priority": consumer["priority"],
                "outcome": consumer["outcome"],
                "reason": consumer["reason"],
                "retryCount": retries,
                "criticalPathNs": critical_path,
                "activeWallNs": _union_duration(intervals),
                "summedStageElapsedNs": elapsed,
                "reviewerCiOverlapNs": overlap,
                "stages": stage_summaries,
            }
        )
    critical_path = (
        max(end for _start, end in all_intervals)
        - min(start for start, _end in all_intervals)
        if all_intervals
        else 0
    )
    slowest_consumer = max(
        consumer_summaries,
        key=lambda item: (item["criticalPathNs"], -item["priority"]),
        default=None,
    )
    slowest_stage_name = max(
        totals,
        key=lambda name: (totals[name], -STAGE_ORDER[name]),
        default=None,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "runId": state["runId"],
        "targetVersion": state["targetVersion"],
        "status": state["status"],
        "fleetStages": fleet_stage_summaries,
        "consumers": consumer_summaries,
        "aggregate": {
            "criticalPathNs": critical_path,
            "activeWallNs": _union_duration(all_intervals),
            "summedStageElapsedNs": summed_elapsed,
            "reviewerCiOverlapNs": _intersection_duration(
                all_reviewer_intervals, all_ci_intervals
            ),
            "retryCount": retry_count,
            "activeAttempts": sum(
                stage["active"] for stage in fleet_stage_summaries
            )
            + sum(
                stage["active"]
                for consumer in consumer_summaries
                for stage in consumer["stages"]
            ),
            "slowestConsumer": (
                {
                    "name": slowest_consumer["name"],
                    "criticalPathNs": slowest_consumer["criticalPathNs"],
                }
                if slowest_consumer is not None
                else None
            ),
            "slowestStage": (
                {"name": slowest_stage_name, "elapsedNs": totals[slowest_stage_name]}
                if slowest_stage_name is not None
                else None
            ),
        },
    }


def format_duration(value: int) -> str:
    return f"{value / 1_000_000_000:.3f}s"


def render_human(state: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    aggregate = summary["aggregate"]
    slowest_consumer = aggregate["slowestConsumer"]
    slowest_stage = aggregate["slowestStage"]
    lines = [
        (
            f"fleet timing: {summary['status']} run {summary['runId']} "
            f"target {summary['targetVersion']}"
        ),
        (
            f"critical path: {format_duration(aggregate['criticalPathNs'])}; "
            f"active wall: {format_duration(aggregate['activeWallNs'])}; "
            f"stage elapsed: {format_duration(aggregate['summedStageElapsedNs'])}; "
            f"reviewer/CI overlap: {format_duration(aggregate['reviewerCiOverlapNs'])}; "
            f"retries: {aggregate['retryCount']}"
        ),
        (
            "slowest: "
            + (
                f"consumer {slowest_consumer['name']} "
                f"{format_duration(slowest_consumer['criticalPathNs'])}"
                if slowest_consumer is not None
                else "consumer none"
            )
            + "; "
            + (
                f"stage {slowest_stage['name']} "
                f"{format_duration(slowest_stage['elapsedNs'])}"
                if slowest_stage is not None
                else "stage none"
            )
        ),
    ]
    for consumer in summary["consumers"]:
        lines.append(
            f"- {consumer['name']} · priority {consumer['priority']} · "
            f"{consumer['outcome'] or 'active'} · "
            f"critical {format_duration(consumer['criticalPathNs'])} · "
            f"active {format_duration(consumer['activeWallNs'])} · "
            f"retries {consumer['retryCount']}"
        )
    return "\n".join(lines)


def operation_output(
    state: Mapping[str, Any], operation: str, changed: bool, reading: ClockReading
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "operation": operation,
        "changed": changed,
        "stateKey": f"{state['repositoryDigest'][:12]}/{state['runId']}",
        "record": state,
        "summary": build_summary(state, reading),
    }


def add_scope_arguments(parser: argparse.ArgumentParser) -> None:
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--fleet", action="store_true")
    scope.add_argument("--consumer")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record local, resumable fleet rollout timing evidence."
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--state-home", type=Path)
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--run-id", required=True)
    init.add_argument("--target-version", required=True)
    init.add_argument("--consumer", action="append", required=True)

    stage_start = subparsers.add_parser("stage-start")
    stage_start.add_argument("--run-id", required=True)
    add_scope_arguments(stage_start)
    stage_start.add_argument("--stage", choices=STAGES, required=True)

    stage_end = subparsers.add_parser("stage-end")
    stage_end.add_argument("--run-id", required=True)
    add_scope_arguments(stage_end)
    stage_end.add_argument("--stage", choices=STAGES, required=True)
    stage_end.add_argument("--outcome", choices=sorted(STAGE_OUTCOMES), required=True)
    stage_end.add_argument("--reason")

    consumer_end = subparsers.add_parser("consumer-end")
    consumer_end.add_argument("--run-id", required=True)
    consumer_end.add_argument("--consumer", required=True)
    consumer_end.add_argument(
        "--outcome", choices=sorted(CONSUMER_OUTCOMES), required=True
    )
    consumer_end.add_argument("--reason")

    report = subparsers.add_parser("report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--complete", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    operation = str(args.command)
    try:
        reading = system_reading()
        store = timing_store(args.repo, args.run_id, args.state_home)
        changed = False
        if args.command == "init":
            consumers = [parse_consumer(value) for value in args.consumer]
            state, changed = initialize_store(
                store, args.run_id, args.target_version, consumers, reading
            )
        elif args.command == "stage-start":
            consumer_name = None if args.fleet else safe_token(args.consumer, "consumer")
            state, changed = mutate_state(
                store,
                args.run_id,
                reading,
                lambda current: start_stage(
                    current,
                    consumer_name=consumer_name,
                    stage_name=args.stage,
                    reading=reading,
                ),
            )
        elif args.command == "stage-end":
            consumer_name = None if args.fleet else safe_token(args.consumer, "consumer")
            state, changed = mutate_state(
                store,
                args.run_id,
                reading,
                lambda current: end_stage(
                    current,
                    consumer_name=consumer_name,
                    stage_name=args.stage,
                    outcome=args.outcome,
                    reason=args.reason,
                    reading=reading,
                ),
            )
        elif args.command == "consumer-end":
            name = safe_token(args.consumer, "consumer")
            state, changed = mutate_state(
                store,
                args.run_id,
                reading,
                lambda current: end_consumer(
                    current, name=name, outcome=args.outcome, reason=args.reason
                ),
            )
        elif args.complete:
            state, changed = mutate_state(
                store,
                args.run_id,
                reading,
                lambda current: complete_state(current, reading),
            )
        else:
            state = load_state(store, args.run_id)
        output = operation_output(state, operation, changed, reading)
    except FleetTimingError as exc:
        error = public_error(exc)
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "schemaVersion": SCHEMA_VERSION,
                        "operation": operation,
                        "status": "error",
                        "error": error,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"fleet timing error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(render_human(state, output["summary"]))
        print(f"operation: {operation}; changed: {'yes' if changed else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
