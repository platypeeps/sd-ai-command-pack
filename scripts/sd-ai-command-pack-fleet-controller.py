#!/usr/bin/env python3
"""Persist and advance deterministic sd-ai-command-pack fleet campaigns."""

from __future__ import annotations

import argparse
import copy
import errno
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sd_ai_command_pack_fleet_lib as fleet_lib  # noqa: E402
from sd_ai_command_pack_lib import CommandError, run_git_minimal  # noqa: E402
from sd_ai_command_pack_lib import (  # noqa: E402
    resolve_state_root as _lib_resolve_state_root,
)

SCHEMA_VERSION = 2
REPORT_SCHEMA_VERSION = 1
MAX_EXHAUSTION_RECOVERIES = 2
MAX_STATE_BYTES = 1024 * 1024
LOCK_STALE_SECONDS = 300
SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
UTC_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

LANE_STAGES = (
    "checkout-validation",
    "install-update",
    "install-audit",
    "candidate-prepare",
    "focused-candidate",
    "local-checks",
    "pr-publication",
    "review",
    "merge-eligibility",
    "merge",
    "post-merge-verification",
)
STAGE_INDEX = {stage: index for index, stage in enumerate(LANE_STAGES)}
PR_HEAD_STAGES = frozenset(
    {"review", "merge-eligibility", "merge", "post-merge-verification"}
)
PR_HEAD_REPUBLICATION_STAGES = frozenset(
    {"review", "merge-eligibility", "merge"}
)
PR_HEAD_ADVANCED_REASON = "pr-head-advanced"
ACTION_IDENTITY_FIELDS = ("actionId", "attempt", "consumer", "release", "stage")
SIDE_EFFECT_STAGES = frozenset(
    {"install-update", "pr-publication", "review", "merge"}
)
RESULTS = frozenset(
    {
        "passed",
        "at-target",
        "retryable-failure",
        "product-failure",
        "review-finding",
        "ownership-skip",
        "permanent-incompatibility",
        "operator-decision",
        "ambiguous",
    }
)
REASON_REQUIRED = RESULTS - {"passed", "at-target"}
RECOVERY_KINDS = frozenset(
    {"pack-blocker", "retry-exhausted", "operator-decision"}
)
OPERATOR_DECISIONS = frozenset({"proceed", "decline"})
PACK_BLOCKER_RECOVERY_FIELDS = {
    "consumer",
    "correctiveRelease",
    "fromActionId",
    "fromAttempt",
    "fromBlocker",
    "fromHead",
    "fromPrNumber",
    "fromStage",
    "kind",
    "recordedAt",
    "toAttempt",
    "toStage",
}
EXHAUSTION_RECOVERY_FIELDS = {
    "consumer",
    "fromActionId",
    "fromAttempt",
    "fromBlocker",
    "fromStage",
    "kind",
    "recordedAt",
    "toAttempt",
    "toStage",
}
OPERATOR_DECISION_RECOVERY_FIELDS = {
    "consumer",
    "decidedBy",
    "decision",
    "decisionHead",
    "fromActionId",
    "fromAttempt",
    "fromBlocker",
    "fromStage",
    "kind",
    "recordedAt",
    "toAttempt",
    "toStage",
}
TERMINAL_RESULTS = frozenset(
    {
        "at-target",
        "merged",
        "pr-open",
        "retry-exhausted",
        "product-failure",
        "review-finding",
        "ownership-skip",
        "permanent-incompatibility",
        "operator-decision",
    }
)


class FleetControllerError(ValueError):
    """Raised when campaign state or a transition is unsafe."""


def _action_identity(action: Mapping[str, Any]) -> dict[str, Any]:
    return {key: action[key] for key in ACTION_IDENTITY_FIELDS}


class _UnsafeSiblingPath(OSError):
    """Path-policy rejection for a trusted sibling-module load: symlink, any
    non-regular node (socket / FIFO / directory), a missing path, or a platform
    without ``O_NOFOLLOW``. Distinct from an arbitrary open/read ``OSError`` so a
    caller can route path-policy failures through its own boundary while a real
    I/O fault still propagates unchanged."""


class _SiblingLoadError(ImportError):
    """The import spec/loader could not be constructed for an already path-safe
    sibling."""


# errno values where the path itself violates policy: a missing final component,
# a symlinked final component (``ELOOP`` under ``O_NOFOLLOW``), or a non-directory
# in the parent chain. Any other open/read errno is a genuine I/O fault.
_PATH_POLICY_ERRNOS = frozenset(
    value
    for value in (getattr(errno, name, None) for name in ("ENOENT", "ELOOP", "ENOTDIR"))
    if value is not None
)


def _read_trusted_sibling_source(path: Path) -> bytes:
    """Read a sibling module's source with no TOCTOU window.

    Fails closed when ``O_NOFOLLOW`` is unavailable. An advisory ``lstat`` picks
    the caller branch for an unsafe path (missing / symlink / any non-regular
    node) but never authorizes a read; the authoritative gate is the fd-anchored
    ``O_NOFOLLOW`` open plus same-descriptor ``fstat``. ``O_NONBLOCK`` keeps a
    FIFO from blocking the open. Executes nothing. Raises ``_UnsafeSiblingPath``
    for a path-policy failure and lets any other open/read ``OSError`` propagate
    unchanged.
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise _UnsafeSiblingPath("O_NOFOLLOW unavailable; refusing sibling load")
    try:
        advisory = os.lstat(path)
    except OSError as error:
        raise _UnsafeSiblingPath(str(error)) from error
    if stat.S_ISLNK(advisory.st_mode) or not stat.S_ISREG(advisory.st_mode):
        raise _UnsafeSiblingPath(f"{path} is not a regular file")
    flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno in _PATH_POLICY_ERRNOS:
            raise _UnsafeSiblingPath(str(error)) from error
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeSiblingPath(f"{path} is not a regular file")
        chunks = []
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _exec_sibling_module(source, path, module_name, *, register):
    """Compile and exec already-read (fd-verified) source into a fresh module.

    The module object is built with the real ``spec_from_file_location`` +
    ``module_from_spec`` pair, so its metadata matches the retired loader
    exactly; neither call reads or executes the file. Execution runs on the bytes
    already read from the verified descriptor, never ``loader.exec_module``.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise _SiblingLoadError(f"cannot construct loader for {path}")
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[module_name] = module
    code = compile(source, str(path), "exec")
    # Trusted sibling; source read from an fd verified regular + non-symlink.
    exec(code, module.__dict__)  # nosec B102
    return module


def _wave_planner() -> Any:
    path = SCRIPT_DIR / "sd-ai-command-pack-fleet-wave-plan.py"
    try:
        source = _read_trusted_sibling_source(path)
        return _exec_sibling_module(
            source,
            path,
            "sd_ai_command_pack_fleet_wave_plan_for_controller",
            register=False,
        )
    except (_UnsafeSiblingPath, _SiblingLoadError) as error:
        raise FleetControllerError("fleet wave planner cannot be loaded") from error


WAVE_PLANNER = _wave_planner()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_token(value: object, label: str) -> str:
    if not isinstance(value, str) or not SAFE_TOKEN_RE.fullmatch(value):
        raise FleetControllerError(f"{label} must be a safe identifier")
    return value


def full_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not FULL_SHA_RE.fullmatch(value):
        raise FleetControllerError(f"{label} must be a lowercase full Git SHA")
    return value


def utc_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        raise FleetControllerError(f"{label} must be a UTC timestamp")
    try:
        time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise FleetControllerError(f"{label} must be a UTC timestamp") from None
    return value


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest_path(path: Path) -> str:
    return _digest_text(str(path.expanduser().resolve()))


def _load_json_with_digest(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        inspected = path.lstat()
    except FileNotFoundError:
        raise FleetControllerError(f"{label} is missing") from None
    except OSError:
        raise FleetControllerError(f"{label} cannot be inspected") from None
    if stat.S_ISLNK(inspected.st_mode) or not stat.S_ISREG(inspected.st_mode):
        raise FleetControllerError(f"{label} must be a regular file")
    if inspected.st_size > MAX_STATE_BYTES:
        raise FleetControllerError(f"{label} exceeds {MAX_STATE_BYTES} bytes")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (inspected.st_dev, inspected.st_ino)
        ):
            raise FleetControllerError(f"{label} changed during inspection")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            content = stream.read(MAX_STATE_BYTES + 1)
    except FleetControllerError:
        raise
    except OSError:
        raise FleetControllerError(f"{label} cannot be opened safely") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(content) > MAX_STATE_BYTES:
        raise FleetControllerError(f"{label} exceeds {MAX_STATE_BYTES} bytes")
    try:
        payload = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError):
        raise FleetControllerError(f"{label} is not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise FleetControllerError(f"{label} must be a JSON object")
    return payload, hashlib.sha256(content).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload, _digest = _load_json_with_digest(path, label)
    return payload


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    except (TypeError, ValueError) as error:
        raise FleetControllerError(
            f"campaign state is not JSON serializable: {error}"
        ) from error
    if len(payload) > MAX_STATE_BYTES:
        raise FleetControllerError(
            f"campaign state exceeds {MAX_STATE_BYTES} bytes"
        )
    return payload


def _default_campaign_root() -> Path:
    """Return the campaign subdirectory of the shared user-local state root.

    ``resolve_state_root`` skips a relative ``XDG_STATE_HOME`` and falls through
    to the home root; this module has always rejected that outright, so the
    check is kept here to preserve the ``FleetControllerError``.
    """

    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    if configured and not Path(configured).expanduser().is_absolute():
        raise FleetControllerError("state home must be an absolute path")
    try:
        return _lib_resolve_state_root() / "fleet-campaigns"
    except CommandError as error:
        raise FleetControllerError(str(error)) from error


class CampaignStore:
    def __init__(self, repo: Path, campaign: str, state_home: Path | None = None):
        self.repo = repo.expanduser().resolve()
        self.campaign = safe_token(campaign, "campaign")
        self.repository_digest = _digest_path(self.repo)
        root = (state_home or _default_campaign_root()).expanduser()
        if not root.is_absolute():
            raise FleetControllerError("state home must be an absolute path")
        if root.is_symlink():
            raise FleetControllerError("campaign state home must not be a symlink")
        self.directory = root / self.repository_digest
        self.state_path = self.directory / f"{self.campaign}.json"
        self.lock_path = self.directory / f"{self.campaign}.lock"

    def _prepare_directory(self) -> None:
        if self.directory.is_symlink():
            raise FleetControllerError("campaign state directory must not be a symlink")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise FleetControllerError("campaign state directory is unusable")
        os.chmod(self.directory, 0o700)

    def _create_lock(self) -> int:
        try:
            return os.open(
                self.lock_path,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            raise
        except OSError:
            raise FleetControllerError("campaign lock cannot be created") from None

    def load(self) -> dict[str, Any]:
        state = _normalize_state(_load_json(self.state_path, "campaign state"))
        validate_state(state)
        if state["repositoryDigest"] != self.repository_digest:
            raise FleetControllerError("campaign repository identity does not match")
        if state["campaignId"] != self.campaign:
            raise FleetControllerError("campaign identity does not match")
        return state

    def write(self, state: Mapping[str, Any]) -> None:
        validate_state(state)
        payload = _json_bytes(state)
        if self.directory.is_symlink() or self.state_path.is_symlink():
            raise FleetControllerError("campaign state path must not be a symlink")
        self._prepare_directory()
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.campaign}.", suffix=".tmp", dir=self.directory
        )
        try:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(descriptor, 0o600)
            else:
                os.chmod(temporary, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_path)
            os.chmod(self.state_path, 0o600)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                Path(temporary).unlink()
            except FileNotFoundError:
                pass

    @contextmanager
    def locked(self) -> Iterator[None]:
        if self.directory.is_symlink() or self.lock_path.is_symlink():
            raise FleetControllerError("campaign lock path must not be a symlink")
        self._prepare_directory()
        try:
            descriptor = self._create_lock()
        except FileExistsError:
            try:
                age = time.time() - self.lock_path.stat().st_mtime
            except OSError:
                age = 0
            if age <= LOCK_STALE_SECONDS:
                raise FleetControllerError("campaign state is busy") from None
            try:
                self.lock_path.unlink()
            except OSError:
                raise FleetControllerError(
                    "stale campaign lock cannot be recovered"
                ) from None
            try:
                descriptor = self._create_lock()
            except FileExistsError:
                raise FleetControllerError("campaign state is busy") from None
        try:
            os.write(descriptor, f"{os.getpid()}\n".encode())
            os.close(descriptor)
            yield
        finally:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass


def _strict_fields(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(fields - actual)
    unknown = sorted(actual - fields)
    if missing:
        raise FleetControllerError(f"{label} is missing field: {missing[0]}")
    if unknown:
        raise FleetControllerError(f"{label} has unknown field: {unknown[0]}")


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("schemaVersion") == 1:
        # One-way migration to schema 2: recovery rows became a tagged union on
        # "kind", and every row written at schema 1 was a pack-blocker recovery.
        # The copies below keep the caller's mapping and its nested rows intact.
        state = dict(state)
        if "recoveries" not in state:
            state["recoveries"] = []
        elif isinstance(state["recoveries"], list):
            state["recoveries"] = [
                {**recovery, "kind": "pack-blocker"}
                if isinstance(recovery, dict) and "kind" not in recovery
                else recovery
                for recovery in state["recoveries"]
            ]
        state.setdefault("allowParkedCanary", False)
        state["schemaVersion"] = 2
        return state
    if state.get("schemaVersion") == SCHEMA_VERSION and (
        "recoveries" not in state or "allowParkedCanary" not in state
    ):
        state = dict(state)
        state.setdefault("recoveries", [])
        # allowParkedCanary is an additive optional field (no schema bump): a
        # campaign planned before it existed defaults to the safe halt-on-parked
        # behavior and loads unchanged.
        state.setdefault("allowParkedCanary", False)
    return state


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FleetControllerError(f"{label} must be an integer >= {minimum}")
    return value


def validate_action(value: object, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise FleetControllerError(f"{label} must be an object or null")
    _strict_fields(
        value,
        {
            "actionId",
            "attempt",
            "consumer",
            "issuedAt",
            "release",
            "sideEffect",
            "stage",
            "timeoutSeconds",
        },
        label,
    )
    safe_token(value["actionId"], f"{label} actionId")
    _integer(value["attempt"], f"{label} attempt", 1)
    if value["consumer"] is not None:
        safe_token(value["consumer"], f"{label} consumer")
    safe_token(value["release"], f"{label} release")
    if not isinstance(value["sideEffect"], bool):
        raise FleetControllerError(f"{label} sideEffect must be boolean")
    stage = safe_token(value["stage"], f"{label} stage")
    if stage != "preflight" and stage not in STAGE_INDEX:
        raise FleetControllerError(f"{label} stage is invalid")
    _integer(value["timeoutSeconds"], f"{label} timeoutSeconds", 1)
    utc_timestamp(value["issuedAt"], f"{label} issuedAt")


def _validate_receipt_semantics(
    *,
    result: str,
    reason_code: str | None,
    blocker: str | None,
    pack_blocker: bool,
    head: str | None,
    pr_number: int | None,
    stage: str,
) -> None:
    if (result in REASON_REQUIRED) != (reason_code is not None):
        requirement = "requires" if result in REASON_REQUIRED else "forbids"
        raise FleetControllerError(f"result {result} {requirement} a reason code")
    if reason_code == PR_HEAD_ADVANCED_REASON:
        if result != "retryable-failure" or stage not in PR_HEAD_REPUBLICATION_STAGES:
            raise FleetControllerError(
                f"reason {PR_HEAD_ADVANCED_REASON} requires a retryable-failure "
                "at review, merge-eligibility, or merge"
            )
        if head is None or pr_number is None:
            raise FleetControllerError(
                f"reason {PR_HEAD_ADVANCED_REASON} requires head and PR number"
            )
        if blocker is not None or pack_blocker:
            raise FleetControllerError(
                f"reason {PR_HEAD_ADVANCED_REASON} forbids blocker evidence"
            )
    if result in {"passed", "at-target"} and (blocker is not None or pack_blocker):
        raise FleetControllerError(f"result {result} forbids blocker evidence")
    if stage in PR_HEAD_STAGES and head is None:
        raise FleetControllerError(f"{stage} receipt requires head")
    if result == "passed" and stage == "pr-publication" and (
        head is None or pr_number is None
    ):
        raise FleetControllerError("PR publication requires head and PR number")
    if result == "at-target" and stage != "checkout-validation":
        raise FleetControllerError(
            "at-target is valid only during checkout validation"
        )


def validate_receipt(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise FleetControllerError(f"{label} must be an object")
    _strict_fields(
        value,
        {
            "actionId",
            "attempt",
            "blocker",
            "consumer",
            "head",
            "packBlocker",
            "prNumber",
            "reasonCode",
            "recordedAt",
            "release",
            "result",
            "stage",
        },
        label,
    )
    safe_token(value["actionId"], f"{label} actionId")
    _integer(value["attempt"], f"{label} attempt", 1)
    if value["consumer"] is not None:
        safe_token(value["consumer"], f"{label} consumer")
    if value["head"] is not None:
        full_sha(value["head"], f"{label} head")
    if value["prNumber"] is not None:
        _integer(value["prNumber"], f"{label} prNumber", 1)
    for field in ("blocker", "reasonCode"):
        if value[field] is not None:
            safe_token(value[field], f"{label} {field}")
    if not isinstance(value["packBlocker"], bool):
        raise FleetControllerError(f"{label} packBlocker must be boolean")
    safe_token(value["release"], f"{label} release")
    if value["result"] not in RESULTS:
        raise FleetControllerError(f"{label} result is invalid")
    stage = safe_token(value["stage"], f"{label} stage")
    if stage != "preflight" and stage not in STAGE_INDEX:
        raise FleetControllerError(f"{label} stage is invalid")
    utc_timestamp(value["recordedAt"], f"{label} recordedAt")
    _validate_receipt_semantics(
        result=value["result"],
        reason_code=value["reasonCode"],
        blocker=value["blocker"],
        pack_blocker=value["packBlocker"],
        head=value["head"],
        pr_number=value["prNumber"],
        stage=stage,
    )


def validate_lane(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise FleetControllerError(f"{label} must be an object")
    _strict_fields(
        value,
        {
            "attempt",
            "blocker",
            "candidateTimeoutSeconds",
            "checkoutDigest",
            "checkoutPath",
            "cohort",
            "head",
            "issuedAction",
            "name",
            "packBlocker",
            "prNumber",
            "priority",
            "receipts",
            "result",
            "stage",
            "status",
        },
        label,
    )
    safe_token(value["name"], f"{label} name")
    safe_token(value["cohort"], f"{label} cohort")
    _integer(value["priority"], f"{label} priority")
    _integer(value["candidateTimeoutSeconds"], f"{label} candidateTimeoutSeconds", 1)
    _integer(value["attempt"], f"{label} attempt", 1)
    if not isinstance(value["checkoutPath"], str) or not value["checkoutPath"]:
        raise FleetControllerError(f"{label} checkoutPath must be a string")
    checkout_path = Path(value["checkoutPath"])
    if not checkout_path.is_absolute():
        raise FleetControllerError(f"{label} checkoutPath must be absolute")
    if not isinstance(value["checkoutDigest"], str) or len(value["checkoutDigest"]) != 64:
        raise FleetControllerError(f"{label} checkoutDigest is invalid")
    if value["checkoutDigest"] != _digest_path(checkout_path):
        raise FleetControllerError(
            f"{label} checkoutDigest does not match checkoutPath"
        )
    if value["stage"] not in STAGE_INDEX:
        raise FleetControllerError(f"{label} stage is invalid")
    if value["status"] not in {"waiting", "issued", "reconcile", "terminal"}:
        raise FleetControllerError(f"{label} status is invalid")
    if value["result"] is not None and value["result"] not in TERMINAL_RESULTS:
        raise FleetControllerError(f"{label} result is invalid")
    if (value["status"] == "terminal") != (value["result"] is not None):
        raise FleetControllerError(
            f"{label} terminal status and result must be consistent"
        )
    if value["blocker"] is not None:
        safe_token(value["blocker"], f"{label} blocker")
    if not isinstance(value["packBlocker"], bool):
        raise FleetControllerError(f"{label} packBlocker must be boolean")
    if value["head"] is not None:
        full_sha(value["head"], f"{label} head")
    if value["prNumber"] is not None:
        _integer(value["prNumber"], f"{label} prNumber", 1)
    validate_action(value["issuedAction"], f"{label} issuedAction")
    if value["status"] == "issued" and value["issuedAction"] is None:
        raise FleetControllerError(f"{label} issued status requires issuedAction")
    if value["status"] != "issued" and value["issuedAction"] is not None:
        raise FleetControllerError(f"{label} issuedAction requires issued status")
    if not isinstance(value["receipts"], list):
        raise FleetControllerError(f"{label} receipts must be an array")
    head_epoch: str | None = None
    for index, receipt in enumerate(value["receipts"]):
        validate_receipt(receipt, f"{label} receipts[{index}]")
        if receipt["stage"] == "pr-publication" and receipt["result"] == "passed":
            head_epoch = receipt["head"]
        elif receipt["stage"] in PR_HEAD_STAGES and receipt["head"] != head_epoch:
            raise FleetControllerError(
                f"{label} receipts[{index}] head does not match its publication epoch or current PR head"
            )
    if head_epoch is not None and value["head"] != head_epoch:
        raise FleetControllerError(f"{label} head does not match the latest publication")


def validate_recovery(value: object, label: str) -> None:
    if not isinstance(value, dict):
        raise FleetControllerError(f"{label} must be an object")
    kind = value.get("kind")
    if kind not in RECOVERY_KINDS:
        raise FleetControllerError(f"{label} kind is invalid")
    _strict_fields(
        value,
        {
            "pack-blocker": PACK_BLOCKER_RECOVERY_FIELDS,
            "retry-exhausted": EXHAUSTION_RECOVERY_FIELDS,
            "operator-decision": OPERATOR_DECISION_RECOVERY_FIELDS,
        }[kind],
        label,
    )
    safe_token(value["consumer"], f"{label} consumer")
    safe_token(value["fromActionId"], f"{label} fromActionId")
    _integer(value["fromAttempt"], f"{label} fromAttempt", 1)
    safe_token(value["fromBlocker"], f"{label} fromBlocker")
    utc_timestamp(value["recordedAt"], f"{label} recordedAt")
    _integer(value["toAttempt"], f"{label} toAttempt", 1)
    if kind == "pack-blocker":
        safe_token(value["correctiveRelease"], f"{label} correctiveRelease")
        full_sha(value["fromHead"], f"{label} fromHead")
        _integer(value["fromPrNumber"], f"{label} fromPrNumber", 1)
        if value["fromStage"] != "merge":
            raise FleetControllerError(f"{label} fromStage must be merge")
        if value["toStage"] != "pr-publication":
            raise FleetControllerError(f"{label} toStage must be pr-publication")
        return
    if value["fromStage"] not in STAGE_INDEX:
        raise FleetControllerError(f"{label} fromStage is invalid")
    if value["toStage"] != value["fromStage"]:
        raise FleetControllerError(f"{label} toStage must match fromStage")
    if kind != "operator-decision":
        return
    if value["decision"] not in OPERATOR_DECISIONS:
        raise FleetControllerError(f"{label} decision is invalid")
    safe_token(value["decidedBy"], f"{label} decidedBy")
    full_sha(value["decisionHead"], f"{label} decisionHead")
    # A decline records the decision without reviving the lane, so its
    # toAttempt is the attempt the lane is staying on rather than a new one.
    if value["decision"] == "decline" and value["toAttempt"] != value["fromAttempt"]:
        raise FleetControllerError(
            f"{label} decline must not advance the lane attempt"
        )


def validate_state(state: Mapping[str, Any]) -> None:
    _strict_fields(
        state,
        {
            "allowParkedCanary",
            "campaignId",
            "createdAt",
            "fleetManifest",
            "fleetManifestDigest",
            "lanes",
            "manifestConsumers",
            "noMerge",
            "preflight",
            "recoveries",
            "release",
            "repositoryDigest",
            "schemaVersion",
            "status",
            "updatedAt",
        },
        "campaign state",
    )
    if state["schemaVersion"] != SCHEMA_VERSION:
        raise FleetControllerError(
            f"campaign schemaVersion must be {SCHEMA_VERSION}"
        )
    safe_token(state["campaignId"], "campaignId")
    safe_token(state["release"], "release")
    utc_timestamp(state["createdAt"], "createdAt")
    utc_timestamp(state["updatedAt"], "updatedAt")
    if not isinstance(state["repositoryDigest"], str) or len(state["repositoryDigest"]) != 64:
        raise FleetControllerError("repositoryDigest is invalid")
    if not isinstance(state["fleetManifest"], str) or not state["fleetManifest"]:
        raise FleetControllerError("fleetManifest must be a string")
    if not Path(state["fleetManifest"]).is_absolute():
        raise FleetControllerError("fleetManifest must be an absolute path")
    if not isinstance(state["fleetManifestDigest"], str) or len(state["fleetManifestDigest"]) != 64:
        raise FleetControllerError("fleetManifestDigest is invalid")
    if not isinstance(state["noMerge"], bool):
        raise FleetControllerError("noMerge must be boolean")
    if not isinstance(state["allowParkedCanary"], bool):
        raise FleetControllerError("allowParkedCanary must be boolean")
    if state["status"] not in {"active", "blocked", "complete"}:
        raise FleetControllerError("campaign status is invalid")
    if not isinstance(state["manifestConsumers"], list) or not state["manifestConsumers"]:
        raise FleetControllerError("manifestConsumers must be a non-empty array")
    manifest_names: list[str] = []
    for item in state["manifestConsumers"]:
        manifest_names.append(safe_token(item, "manifest consumer"))
    if len(manifest_names) != len(set(manifest_names)):
        raise FleetControllerError("manifestConsumers must be unique")
    preflight = state["preflight"]
    if not isinstance(preflight, dict):
        raise FleetControllerError("preflight must be an object")
    _strict_fields(
        preflight,
        {"attempt", "issuedAction", "receipts", "status"},
        "preflight",
    )
    _integer(preflight["attempt"], "preflight attempt", 1)
    if preflight["status"] not in {"waiting", "issued", "passed", "reconcile", "blocked"}:
        raise FleetControllerError("preflight status is invalid")
    validate_action(preflight["issuedAction"], "preflight issuedAction")
    if preflight["status"] == "issued" and preflight["issuedAction"] is None:
        raise FleetControllerError("issued preflight requires issuedAction")
    if preflight["status"] != "issued" and preflight["issuedAction"] is not None:
        raise FleetControllerError("preflight issuedAction requires issued status")
    if not isinstance(preflight["receipts"], list):
        raise FleetControllerError("preflight receipts must be an array")
    for index, receipt in enumerate(preflight["receipts"]):
        validate_receipt(receipt, f"preflight receipts[{index}]")
        if receipt["consumer"] is not None or receipt["release"] != state["release"]:
            raise FleetControllerError(
                f"preflight receipts[{index}] identity does not match the campaign"
            )
    preflight_action = preflight["issuedAction"]
    if preflight_action is not None and (
        preflight_action["consumer"] is not None
        or preflight_action["stage"] != "preflight"
        or preflight_action["attempt"] != preflight["attempt"]
        or preflight_action["release"] != state["release"]
    ):
        raise FleetControllerError(
            "preflight issuedAction identity does not match the campaign"
        )
    if not isinstance(state["lanes"], list) or not state["lanes"]:
        raise FleetControllerError("lanes must be a non-empty array")
    names: list[str] = []
    priorities: list[int] = []
    for index, lane in enumerate(state["lanes"]):
        validate_lane(lane, f"lanes[{index}]")
        names.append(lane["name"])
        priorities.append(lane["priority"])
        action = lane["issuedAction"]
        if action is not None and (
            action["consumer"] != lane["name"]
            or action["stage"] != lane["stage"]
            or action["attempt"] != lane["attempt"]
            or action["release"] != state["release"]
        ):
            raise FleetControllerError(
                f"lanes[{index}] issuedAction identity does not match the lane"
            )
        for receipt in lane["receipts"]:
            if (
                receipt["consumer"] != lane["name"]
                or receipt["release"] != state["release"]
            ):
                raise FleetControllerError(
                    f"lanes[{index}] receipt identity does not match the lane"
                )
    if len(names) != len(set(names)) or any(name not in manifest_names for name in names):
        raise FleetControllerError("lane consumer identities are invalid")
    if priorities != sorted(priorities) or len(priorities) != len(set(priorities)):
        raise FleetControllerError("lane priorities must be unique and ordered")
    if not isinstance(state["recoveries"], list):
        raise FleetControllerError("recoveries must be an array")
    recovery_keys: set[tuple[str, str]] = set()
    for index, recovery in enumerate(state["recoveries"]):
        validate_recovery(recovery, f"recoveries[{index}]")
        if recovery["consumer"] not in names:
            raise FleetControllerError(
                f"recoveries[{index}] consumer is outside the campaign"
            )
        key = (recovery["consumer"], recovery["fromActionId"])
        if key in recovery_keys:
            raise FleetControllerError("recoveries must have unique source actions")
        recovery_keys.add(key)


def _manifest(path: Path) -> tuple[dict[str, Any], list[Any], Any, str]:
    payload, digest = _load_json_with_digest(path, "fleet manifest")
    try:
        consumers, policy = fleet_lib.parse_fleet_manifest(payload)
    except fleet_lib.FleetConfigError as error:
        raise FleetControllerError(str(error)) from None
    return payload, consumers, policy, digest


def _cohort_by_consumer(policy: Any) -> dict[str, str]:
    return {
        consumer: cohort.name
        for cohort in policy.cohorts
        for consumer in cohort.consumers
    }


def _pack_release(path: Path) -> str:
    payload = _load_json(path, "pack manifest")
    value = payload.get("version")
    return safe_token(value, "pack manifest version")


def _checkout_overrides(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in values:
        name, separator, path = raw.partition("=")
        if not separator or not path:
            raise FleetControllerError("checkout must use NAME=PATH")
        name = safe_token(name, "checkout consumer")
        if name in result:
            raise FleetControllerError(f"checkout repeats consumer {name}")
        result[name] = Path(path).expanduser().resolve()
    return result


def new_state(
    *,
    repo: Path,
    campaign: str,
    release: str,
    fleet_path: Path,
    pack_manifest_path: Path,
    selected: Sequence[str] = (),
    checkout_overrides: Mapping[str, Path] | None = None,
    no_merge: bool = False,
    allow_parked_canary: bool = False,
) -> dict[str, Any]:
    campaign = safe_token(campaign, "campaign")
    release = safe_token(release, "release")
    actual_release = _pack_release(pack_manifest_path)
    if release != actual_release:
        raise FleetControllerError(
            f"release {release} does not match pack manifest {actual_release}"
        )
    _payload, consumers, policy, manifest_digest = _manifest(fleet_path)
    known = {consumer.name: consumer for consumer in consumers}
    selected_names = list(selected) if selected else [item.name for item in consumers]
    if len(selected_names) != len(set(selected_names)):
        raise FleetControllerError("selected consumers must be unique")
    unknown = [name for name in selected_names if name not in known]
    if unknown:
        raise FleetControllerError(f"unknown fleet consumer: {unknown[0]}")
    overrides = dict(checkout_overrides or {})
    unknown_overrides = [name for name in overrides if name not in selected_names]
    if unknown_overrides:
        raise FleetControllerError(
            f"checkout override is outside selected consumers: {unknown_overrides[0]}"
        )
    cohort_names = _cohort_by_consumer(policy)
    lanes: list[dict[str, Any]] = []
    for consumer in consumers:
        if consumer.name not in selected_names:
            continue
        checkout = overrides.get(
            consumer.name, Path(consumer.path_hint)
        ).expanduser().resolve()
        lanes.append(
            {
                "attempt": 1,
                "blocker": None,
                "candidateTimeoutSeconds": consumer.candidate_timeout_seconds,
                "checkoutDigest": _digest_path(checkout),
                "checkoutPath": str(checkout),
                "cohort": cohort_names[consumer.name],
                "head": None,
                "issuedAction": None,
                "name": consumer.name,
                "packBlocker": False,
                "prNumber": None,
                "priority": consumer.rollout_priority,
                "receipts": [],
                "result": None,
                "stage": LANE_STAGES[0],
                "status": "waiting",
            }
        )
    now = utc_now()
    state = {
        "allowParkedCanary": allow_parked_canary,
        "campaignId": campaign,
        "createdAt": now,
        "fleetManifest": str(fleet_path.expanduser().resolve()),
        "fleetManifestDigest": manifest_digest,
        "lanes": lanes,
        "manifestConsumers": [consumer.name for consumer in consumers],
        "noMerge": no_merge,
        "preflight": {
            "attempt": 1,
            "issuedAction": None,
            "receipts": [],
            "status": "waiting",
        },
        "recoveries": [],
        "release": release,
        "repositoryDigest": _digest_path(repo),
        "schemaVersion": SCHEMA_VERSION,
        "status": "active",
        "updatedAt": now,
    }
    validate_state(state)
    return state


def _action_id(
    state: Mapping[str, Any], consumer: str | None, stage: str, attempt: int
) -> str:
    identity = ":".join(
        (
            state["campaignId"],
            state["release"],
            consumer or "campaign",
            stage,
            str(attempt),
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _new_action(
    state: Mapping[str, Any], lane: Mapping[str, Any] | None, stage: str, attempt: int
) -> dict[str, Any]:
    consumer = lane["name"] if lane is not None else None
    timeout = (
        lane["candidateTimeoutSeconds"]
        if lane is not None and stage in {"candidate-prepare", "focused-candidate", "local-checks"}
        else 900
    )
    return {
        "actionId": _action_id(state, consumer, stage, attempt),
        "attempt": attempt,
        "consumer": consumer,
        "issuedAt": utc_now(),
        "release": state["release"],
        "sideEffect": stage in SIDE_EFFECT_STAGES,
        "stage": stage,
        "timeoutSeconds": timeout,
    }


def _current_attempt_receipts(lane: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        receipt
        for receipt in lane["receipts"]
        if receipt["attempt"] == lane["attempt"]
    ]


def _observations(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    selected = {lane["name"]: lane for lane in state["lanes"]}
    observations: dict[str, dict[str, Any]] = {}
    for name in state["manifestConsumers"]:
        lane = selected.get(name)
        if lane is None:
            observations[name] = {
                "state": "at-target",
                "packBlocker": False,
                "parked": False,
            }
            continue
        result = lane["result"]
        if result == "at-target":
            observed = "at-target"
        elif result == "merged":
            observed = "merged"
        elif result == "pr-open":
            observed = "pr-open"
        elif result == "ownership-skip":
            observed = "skipped"
        elif result in {"product-failure", "review-finding", "retry-exhausted"}:
            observed = "blocked" if lane["packBlocker"] else "failed"
        elif result in {"permanent-incompatibility", "operator-decision"}:
            observed = "blocked"
        elif (
            lane["stage"] == "checkout-validation"
            and not _current_attempt_receipts(lane)
            and lane["status"] == "waiting"
        ):
            observed = "pending"
        elif lane["stage"] == "merge" and lane["status"] == "waiting":
            observed = "ready"
        else:
            observed = "in-flight"
        observations[name] = {
            "state": observed,
            "packBlocker": lane["packBlocker"],
            "parked": result == "operator-decision",
        }
    return observations


def _planner(state: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(state["fleetManifest"])
    _payload, _consumers, policy, digest = _manifest(path)
    if digest != state["fleetManifestDigest"]:
        raise FleetControllerError("fleet manifest changed during campaign")
    try:
        return WAVE_PLANNER.plan_rollout(
            policy,
            _observations(state),
            no_merge=state["noMerge"],
            allow_parked_canary=state["allowParkedCanary"],
        )
    except WAVE_PLANNER.FleetWavePlanError as error:
        raise FleetControllerError(str(error)) from None


def _eligible_lanes(state: Mapping[str, Any], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    starts = set(plan["canStart"])
    merge_candidate = plan["mergeCandidate"]
    eligible: list[dict[str, Any]] = []
    for lane in state["lanes"]:
        if lane["status"] != "waiting" or lane["result"] is not None:
            continue
        if lane["stage"] == "checkout-validation":
            if not _current_attempt_receipts(lane) and lane["name"] in starts:
                eligible.append(lane)
            continue
        if lane["stage"] == "merge":
            if lane["name"] == merge_candidate:
                eligible.append(lane)
            continue
        eligible.append(lane)
    return eligible


def issue_next(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state["status"] == "complete":
        return []
    preflight = state["preflight"]
    if preflight["status"] == "waiting":
        action = _new_action(state, None, "preflight", preflight["attempt"])
        preflight["issuedAction"] = action
        preflight["status"] = "issued"
        state["updatedAt"] = utc_now()
        return [action]
    if preflight["status"] != "passed":
        return []
    if any(lane["status"] == "reconcile" for lane in state["lanes"]):
        state["status"] = "blocked"
        return []
    plan = _planner(state)
    actions: list[dict[str, Any]] = []
    for lane in _eligible_lanes(state, plan):
        action = _new_action(state, lane, lane["stage"], lane["attempt"])
        lane["issuedAction"] = action
        lane["status"] = "issued"
        actions.append(action)
    if actions:
        state["updatedAt"] = utc_now()
    _refresh_campaign_status(state, plan=plan)
    return actions


def _receipt_core(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "recordedAt"}


def _existing_receipt(state: Mapping[str, Any], action_id: str) -> dict[str, Any] | None:
    receipts = list(state["preflight"]["receipts"])
    for lane in state["lanes"]:
        receipts.extend(lane["receipts"])
    return next((item for item in receipts if item["actionId"] == action_id), None)


def _build_receipt(
    action: Mapping[str, Any],
    *,
    result: str,
    reason_code: str | None,
    blocker: str | None,
    pack_blocker: bool,
    head: str | None,
    pr_number: int | None,
) -> dict[str, Any]:
    if result not in RESULTS:
        raise FleetControllerError("result is invalid")
    if reason_code is not None:
        reason_code = safe_token(reason_code, "reason code")
    if blocker is not None:
        blocker = safe_token(blocker, "blocker")
    if head is not None:
        head = full_sha(head, "head")
    if pr_number is not None:
        _integer(pr_number, "PR number", 1)
    _validate_receipt_semantics(
        result=result,
        reason_code=reason_code,
        blocker=blocker,
        pack_blocker=pack_blocker,
        head=head,
        pr_number=pr_number,
        stage=action["stage"],
    )
    return {
        "actionId": action["actionId"],
        "attempt": action["attempt"],
        "blocker": blocker,
        "consumer": action["consumer"],
        "head": head,
        "packBlocker": pack_blocker,
        "prNumber": pr_number,
        "reasonCode": reason_code,
        "recordedAt": utc_now(),
        "release": action["release"],
        "result": result,
        "stage": action["stage"],
    }


def _advance_lane(lane: dict[str, Any], receipt: Mapping[str, Any], no_merge: bool) -> None:
    result = receipt["result"]
    stage = lane["stage"]
    prior_head = lane["head"]
    prior_pr_number = lane["prNumber"]
    if stage in PR_HEAD_STAGES and (
        prior_head is None or receipt["head"] != prior_head
    ):
        raise FleetControllerError("receipt head does not match the current PR head")
    if receipt["reasonCode"] == PR_HEAD_ADVANCED_REASON and (
        prior_pr_number is None or receipt["prNumber"] != prior_pr_number
    ):
        raise FleetControllerError(
            "receipt PR number does not match the current PR number"
        )
    if result == "passed" and stage == "pr-publication" and (
        receipt["head"] is None or receipt["prNumber"] is None
    ):
        raise FleetControllerError("PR publication requires head and PR number")
    if (
        result == "passed"
        and stage == "pr-publication"
        and prior_pr_number is not None
        and receipt["prNumber"] != prior_pr_number
    ):
        raise FleetControllerError(
            "PR republication must reuse the current PR number"
        )
    if receipt["head"] is not None:
        lane["head"] = receipt["head"]
    if receipt["prNumber"] is not None:
        lane["prNumber"] = receipt["prNumber"]
    lane["issuedAction"] = None
    if result == "passed":
        if stage == "merge-eligibility" and no_merge:
            lane["status"] = "terminal"
            lane["result"] = "pr-open"
            return
        if stage == LANE_STAGES[-1]:
            lane["status"] = "terminal"
            lane["result"] = "merged"
            return
        next_stage = LANE_STAGES[STAGE_INDEX[stage] + 1]
        lane["stage"] = next_stage
        lane["attempt"] = _next_stage_attempt(lane, next_stage)
        lane["status"] = "waiting"
        return
    if result == "at-target":
        if stage != "checkout-validation":
            raise FleetControllerError("at-target is valid only during checkout validation")
        lane["status"] = "terminal"
        lane["result"] = "at-target"
        return
    if result == "retryable-failure":
        if lane["attempt"] < 2:
            if receipt["reasonCode"] == PR_HEAD_ADVANCED_REASON:
                lane["stage"] = "pr-publication"
                lane["attempt"] = _next_stage_attempt(lane, "pr-publication")
            else:
                lane["attempt"] += 1
            lane["status"] = "waiting"
        else:
            lane["status"] = "terminal"
            lane["result"] = "retry-exhausted"
            lane["blocker"] = receipt["reasonCode"]
        return
    if result == "ambiguous":
        lane["status"] = "reconcile"
        lane["blocker"] = receipt["reasonCode"]
        return
    lane["status"] = "terminal"
    lane["result"] = result
    lane["blocker"] = receipt["blocker"] or receipt["reasonCode"]
    lane["packBlocker"] = receipt["packBlocker"]


def record_result(
    state: dict[str, Any],
    *,
    action_id: str,
    release: str,
    consumer: str | None,
    result: str,
    reason_code: str | None = None,
    blocker: str | None = None,
    pack_blocker: bool = False,
    head: str | None = None,
    pr_number: int | None = None,
) -> tuple[dict[str, Any], bool]:
    action_id = safe_token(action_id, "action ID")
    if release != state["release"]:
        raise FleetControllerError("receipt release does not match campaign release")
    target: dict[str, Any]
    if consumer is None:
        target = state["preflight"]
    else:
        consumer = safe_token(consumer, "consumer")
        try:
            target = next(lane for lane in state["lanes"] if lane["name"] == consumer)
        except StopIteration:
            raise FleetControllerError("receipt consumer is outside the campaign") from None
    issued = target["issuedAction"]
    existing = _existing_receipt(state, action_id)
    if existing is not None:
        if existing["consumer"] != consumer:
            raise FleetControllerError("action already has a conflicting receipt")
        candidate_action = _action_identity(existing)
    else:
        if issued is None or issued["actionId"] != action_id:
            raise FleetControllerError(
                "action ID is not currently issued for this target"
            )
        candidate_action = issued
    receipt = _build_receipt(
        candidate_action,
        result=result,
        reason_code=reason_code,
        blocker=blocker,
        pack_blocker=pack_blocker,
        head=head,
        pr_number=pr_number,
    )
    if existing is not None:
        if _receipt_core(existing) != _receipt_core(receipt):
            raise FleetControllerError("action already has a conflicting receipt")
        return existing, False
    if consumer is None:
        target["receipts"].append(receipt)
        target["issuedAction"] = None
        if result == "passed":
            target["status"] = "passed"
        elif result == "retryable-failure" and target["attempt"] < 2:
            target["attempt"] += 1
            target["status"] = "waiting"
        elif result == "ambiguous":
            target["status"] = "reconcile"
        else:
            target["status"] = "blocked"
    else:
        trial = copy.deepcopy(target)
        trial["receipts"].append(receipt)
        _advance_lane(trial, receipt, state["noMerge"])
        target.clear()
        target.update(trial)
    state["updatedAt"] = utc_now()
    _refresh_campaign_status(state)
    validate_state(state)
    return receipt, True


def retry_consumer(state: dict[str, Any], consumer: str) -> None:
    consumer = safe_token(consumer, "consumer")
    try:
        lane = next(item for item in state["lanes"] if item["name"] == consumer)
    except StopIteration:
        raise FleetControllerError("consumer is outside the campaign") from None
    if lane["status"] != "terminal" or lane["result"] != "ownership-skip":
        raise FleetControllerError(
            "consumer retry requires a terminal ownership-skip"
        )
    lane["attempt"] += 1
    lane["blocker"] = None
    lane["packBlocker"] = False
    lane["result"] = None
    lane["stage"] = "checkout-validation"
    lane["status"] = "waiting"
    state["status"] = "active"
    state["updatedAt"] = utc_now()


def _next_stage_attempt(lane: Mapping[str, Any], stage: str) -> int:
    attempts = [
        receipt["attempt"]
        for receipt in lane["receipts"]
        if receipt["stage"] == stage
    ]
    return max(attempts, default=0) + 1


def recover_pack_blocker(
    state: dict[str, Any],
    *,
    consumer: str,
    corrective_release: str,
    actual_release: str,
) -> tuple[dict[str, Any], bool]:
    consumer = safe_token(consumer, "consumer")
    corrective_release = safe_token(corrective_release, "corrective release")
    actual_release = safe_token(actual_release, "pack manifest version")
    if corrective_release == state["release"]:
        raise FleetControllerError(
            "corrective release must differ from the campaign target"
        )
    if corrective_release != actual_release:
        raise FleetControllerError(
            "corrective release does not match the current pack manifest"
        )
    try:
        lane = next(item for item in state["lanes"] if item["name"] == consumer)
    except StopIteration:
        raise FleetControllerError("consumer is outside the campaign") from None
    if not lane["receipts"]:
        raise FleetControllerError("consumer has no blocker receipt to recover")
    blocker_receipt = lane["receipts"][-1]
    existing = next(
        (
            item
            for item in state["recoveries"]
            if item["kind"] == "pack-blocker"
            and item["consumer"] == consumer
            and item["fromActionId"] == blocker_receipt["actionId"]
        ),
        None,
    )
    if existing is not None:
        if existing["correctiveRelease"] != corrective_release:
            raise FleetControllerError(
                "corrective recovery source action is already bound to a different release"
            )
        return existing, False
    if (
        lane["status"] != "terminal"
        or lane["result"] != "review-finding"
        or not lane["packBlocker"]
        or lane["stage"] != "merge"
    ):
        raise FleetControllerError(
            "corrective recovery requires a terminal merge-stage pack review-finding"
        )
    if lane["issuedAction"] is not None:
        raise FleetControllerError("corrective recovery cannot replace an issued action")
    if lane["head"] is None or lane["prNumber"] is None:
        raise FleetControllerError("corrective recovery requires an exact PR head")
    if (
        blocker_receipt["stage"] != "merge"
        or blocker_receipt["result"] != "review-finding"
        or not blocker_receipt["packBlocker"]
        or blocker_receipt["blocker"] != lane["blocker"]
        or blocker_receipt["head"] != lane["head"]
        or blocker_receipt["prNumber"] != lane["prNumber"]
    ):
        raise FleetControllerError(
            "corrective recovery blocker receipt does not match the lane"
        )
    to_attempt = _next_stage_attempt(lane, "pr-publication")
    recovery = {
        "consumer": consumer,
        "correctiveRelease": corrective_release,
        "fromActionId": blocker_receipt["actionId"],
        "fromAttempt": blocker_receipt["attempt"],
        "fromBlocker": lane["blocker"],
        "fromHead": lane["head"],
        "fromPrNumber": lane["prNumber"],
        "fromStage": lane["stage"],
        "kind": "pack-blocker",
        "recordedAt": utc_now(),
        "toAttempt": to_attempt,
        "toStage": "pr-publication",
    }
    state["recoveries"].append(recovery)
    lane["attempt"] = to_attempt
    lane["blocker"] = None
    lane["packBlocker"] = False
    lane["result"] = None
    lane["stage"] = "pr-publication"
    lane["status"] = "waiting"
    state["updatedAt"] = utc_now()
    _refresh_campaign_status(state)
    validate_state(state)
    return recovery, True


def recover_retry_exhausted(
    state: dict[str, Any],
    *,
    consumer: str,
    exhausted_action_id: str,
    release: str,
) -> tuple[dict[str, Any], bool]:
    consumer = safe_token(consumer, "consumer")
    exhausted_action_id = safe_token(exhausted_action_id, "exhausted action ID")
    # Deliberately compared against the campaign target rather than the current
    # pack manifest: this transition has no corrective release, so a manifest
    # comparison would make every campaign unrecoverable as soon as the
    # installed pack moved past that campaign's release.
    if release != state["release"]:
        raise FleetControllerError(
            "exhaustion recovery release does not match campaign release"
        )
    try:
        lane = next(item for item in state["lanes"] if item["name"] == consumer)
    except StopIteration:
        raise FleetControllerError("consumer is outside the campaign") from None
    existing = next(
        (
            item
            for item in state["recoveries"]
            if item["kind"] == "retry-exhausted"
            and item["consumer"] == consumer
            and item["fromActionId"] == exhausted_action_id
        ),
        None,
    )
    if existing is not None:
        return existing, False
    if lane["status"] != "terminal" or lane["result"] != "retry-exhausted":
        raise FleetControllerError(
            "exhaustion recovery requires a terminal retry-exhausted lane"
        )
    if not lane["receipts"]:
        raise FleetControllerError("consumer has no exhaustion receipt to recover")
    exhaustion_receipt = lane["receipts"][-1]
    if exhaustion_receipt["actionId"] != exhausted_action_id:
        raise FleetControllerError(
            "exhausted action is not the lane's latest receipt"
        )
    if (
        exhaustion_receipt["stage"] != lane["stage"]
        or exhaustion_receipt["result"] != "retryable-failure"
        or exhaustion_receipt["reasonCode"] != lane["blocker"]
    ):
        raise FleetControllerError(
            "exhaustion recovery receipt does not match the lane"
        )
    if exhaustion_receipt["attempt"] != lane["attempt"]:
        raise FleetControllerError(
            "exhaustion recovery receipt attempt does not match the lane attempt"
        )
    stage = lane["stage"]
    granted = sum(
        1
        for item in state["recoveries"]
        if item["kind"] == "retry-exhausted"
        and item["consumer"] == consumer
        and item["fromStage"] == stage
    )
    if granted >= MAX_EXHAUSTION_RECOVERIES:
        raise FleetControllerError(
            "exhaustion recovery limit is reached for this consumer and stage"
        )
    to_attempt = _next_stage_attempt(lane, stage)
    recovery = {
        "consumer": consumer,
        "fromActionId": exhausted_action_id,
        "fromAttempt": exhaustion_receipt["attempt"],
        "fromBlocker": lane["blocker"],
        "fromStage": stage,
        "kind": "retry-exhausted",
        "recordedAt": utc_now(),
        "toAttempt": to_attempt,
        "toStage": stage,
    }
    state["recoveries"].append(recovery)
    lane["attempt"] = to_attempt
    lane["blocker"] = None
    lane["packBlocker"] = False
    lane["result"] = None
    lane["status"] = "waiting"
    state["updatedAt"] = utc_now()
    _refresh_campaign_status(state)
    validate_state(state)
    return recovery, True


def record_operator_decision(
    state: dict[str, Any],
    *,
    consumer: str,
    decision: str,
    decided_by: str,
    decision_head: str,
    release: str,
) -> tuple[dict[str, Any], bool]:
    """Record the human decision a parked ``operator-decision`` lane waited for.

    The controller parks a lane precisely because a person must choose, and
    until now that was the one terminal state with no way back: ``--retry-consumer``
    wants ``ownership-skip``, ``--recover-consumer`` wants a merge-stage pack
    blocker, and ``--recover-exhausted-consumer`` wants ``retry-exhausted``. A
    lane parked for a decision could therefore never have the decision recorded,
    and an operator who chose to proceed had no supported way to finish the lane.

    ``proceed`` re-enters the lane at the stage it parked on, on a fresh attempt,
    so the remaining stages are issued and recorded through the ordinary receipt
    chain. It stamps nothing terminal by itself. ``decline`` leaves the lane
    exactly where it is and records that this was chosen, so a declined lane is
    distinguishable from one nobody ever answered.
    """

    consumer = safe_token(consumer, "consumer")
    decided_by = safe_token(decided_by, "deciding party")
    full_sha(decision_head, "decision head")
    if decision not in OPERATOR_DECISIONS:
        raise FleetControllerError("decision must be proceed or decline")
    # Compared against the campaign target, not the current pack manifest, for
    # the same reason exhaustion recovery is: this transition has no corrective
    # release, and a manifest comparison would make every campaign undecidable
    # as soon as the installed pack moved past that campaign's release.
    if release != state["release"]:
        raise FleetControllerError(
            "operator decision release does not match campaign release"
        )
    try:
        lane = next(item for item in state["lanes"] if item["name"] == consumer)
    except StopIteration:
        raise FleetControllerError("consumer is outside the campaign") from None
    if not lane["receipts"]:
        raise FleetControllerError("consumer has no decision receipt to answer")
    decision_receipt = lane["receipts"][-1]
    existing = next(
        (
            item
            for item in state["recoveries"]
            if item["kind"] == "operator-decision"
            and item["consumer"] == consumer
            and item["fromActionId"] == decision_receipt["actionId"]
        ),
        None,
    )
    if existing is not None:
        if (
            existing["decision"] != decision
            or existing["decidedBy"] != decided_by
            or existing["decisionHead"] != decision_head
        ):
            raise FleetControllerError(
                "this parked action already carries a different operator decision"
            )
        return existing, False
    if lane["status"] != "terminal" or lane["result"] != "operator-decision":
        raise FleetControllerError(
            "operator decision requires a terminal operator-decision lane"
        )
    if lane["issuedAction"] is not None:
        raise FleetControllerError("operator decision cannot replace an issued action")
    if (
        decision_receipt["stage"] != lane["stage"]
        or decision_receipt["result"] != "operator-decision"
        or decision_receipt["reasonCode"] != lane["blocker"]
        or decision_receipt["attempt"] != lane["attempt"]
    ):
        raise FleetControllerError(
            "operator decision receipt does not match the lane"
        )
    # The decision is bound to the head it was made against, so a lane that
    # moved after the operator looked at it cannot inherit their answer.
    if lane["head"] is None:
        raise FleetControllerError(
            "operator decision requires a lane with a published head"
        )
    if lane["head"] != decision_head:
        raise FleetControllerError(
            "operator decision head does not match the lane head"
        )
    stage = lane["stage"]
    to_attempt = (
        _next_stage_attempt(lane, stage)
        if decision == "proceed"
        else lane["attempt"]
    )
    recovery = {
        "consumer": consumer,
        "decidedBy": decided_by,
        "decision": decision,
        "decisionHead": decision_head,
        "fromActionId": decision_receipt["actionId"],
        "fromAttempt": decision_receipt["attempt"],
        "fromBlocker": lane["blocker"],
        "fromStage": stage,
        "kind": "operator-decision",
        "recordedAt": utc_now(),
        "toAttempt": to_attempt,
        "toStage": stage,
    }
    state["recoveries"].append(recovery)
    if decision == "proceed":
        lane["attempt"] = to_attempt
        lane["blocker"] = None
        lane["packBlocker"] = False
        lane["result"] = None
        lane["status"] = "waiting"
    state["updatedAt"] = utc_now()
    _refresh_campaign_status(state)
    validate_state(state)
    return recovery, True


def resolve_reconciliation(
    state: dict[str, Any],
    *,
    action_id: str,
    release: str,
    consumer: str | None,
    result: str,
    reason_code: str | None = None,
    blocker: str | None = None,
    pack_blocker: bool = False,
    head: str | None = None,
    pr_number: int | None = None,
) -> tuple[dict[str, Any], bool]:
    if release != state["release"]:
        raise FleetControllerError("resolution release does not match campaign release")
    if result == "ambiguous":
        raise FleetControllerError("reconciliation result cannot remain ambiguous")
    action_id = safe_token(action_id, "action ID")
    target: dict[str, Any]
    if consumer is None:
        target = state["preflight"]
    else:
        consumer = safe_token(consumer, "consumer")
        try:
            target = next(lane for lane in state["lanes"] if lane["name"] == consumer)
        except StopIteration:
            raise FleetControllerError("consumer is outside the campaign") from None
    try:
        ambiguous = next(
            receipt
            for receipt in target["receipts"]
            if receipt["actionId"] == action_id and receipt["result"] == "ambiguous"
        )
    except StopIteration:
        raise FleetControllerError("action has no ambiguous receipt to reconcile") from None
    resolution_action = {
        "actionId": hashlib.sha256(f"{action_id}:resolution".encode()).hexdigest(),
        "attempt": ambiguous["attempt"],
        "consumer": consumer,
        "release": release,
        "stage": ambiguous["stage"],
    }
    receipt = _build_receipt(
        resolution_action,
        result=result,
        reason_code=reason_code,
        blocker=blocker,
        pack_blocker=pack_blocker,
        head=head,
        pr_number=pr_number,
    )
    existing = _existing_receipt(state, resolution_action["actionId"])
    if existing is not None:
        if _receipt_core(existing) != _receipt_core(receipt):
            raise FleetControllerError("reconciliation already has a conflicting receipt")
        return existing, False
    if target["status"] != "reconcile":
        raise FleetControllerError("target is not awaiting reconciliation")
    if consumer is None:
        target["receipts"].append(receipt)
        if result == "passed":
            target["status"] = "passed"
        elif result == "retryable-failure" and target["attempt"] < 2:
            target["attempt"] += 1
            target["status"] = "waiting"
        else:
            target["status"] = "blocked"
    else:
        trial = copy.deepcopy(target)
        trial["receipts"].append(receipt)
        _advance_lane(trial, receipt, state["noMerge"])
        target.clear()
        target.update(trial)
    state["updatedAt"] = utc_now()
    _refresh_campaign_status(state)
    validate_state(state)
    return receipt, True


def _refresh_campaign_status(
    state: dict[str, Any], *, plan: Mapping[str, Any] | None = None
) -> None:
    if state["preflight"]["status"] in {"blocked", "reconcile"}:
        state["status"] = "blocked"
        return
    if all(lane["status"] == "terminal" for lane in state["lanes"]):
        state["status"] = "complete"
        return
    if state["preflight"]["status"] != "passed":
        state["status"] = "active"
        return
    if any(lane["status"] == "reconcile" for lane in state["lanes"]):
        state["status"] = "blocked"
        return
    plan = dict(plan or _planner(state))
    state["status"] = "blocked" if plan["stopStarting"] else "active"


def _git_evidence(path: Path, expected_checkout_digest: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "branch": None,
        "checkoutDigestMatches": path.is_dir()
        and _digest_path(path) == expected_checkout_digest,
        "clean": None,
        "exists": path.is_dir(),
        "head": None,
    }
    if not result["exists"]:
        return result
    try:
        head_result = run_git_minimal(
            ["-C", str(path), "rev-parse", "HEAD"], timeout=10
        )
        if head_result.returncode != 0:
            return result
        head = head_result.stdout.strip()
        branch_result = run_git_minimal(
            ["-C", str(path), "branch", "--show-current"], timeout=10
        )
        if branch_result.returncode != 0:
            return result
        branch = branch_result.stdout.strip()
        dirty_result = run_git_minimal(
            ["-C", str(path), "status", "--porcelain"], timeout=10
        )
        if dirty_result.returncode != 0:
            return result
        # Populate the evidence only once all three probes succeed; every
        # earlier return leaves the default result untouched, so there is no
        # partial or misleadingly-defaulted state to reason about.
        result.update(
            {
                "branch": branch or None,
                "clean": not bool(dirty_result.stdout),
                "head": head if FULL_SHA_RE.fullmatch(head) else None,
            }
        )
    except (OSError, subprocess.SubprocessError):
        return result
    return result


def _reconciliation_action(target: Mapping[str, Any]) -> Mapping[str, Any] | None:
    action = target["issuedAction"]
    if action is not None:
        return _action_identity(action)
    if target["status"] != "reconcile":
        return None
    ambiguous = next(
        (
            receipt
            for receipt in reversed(target["receipts"])
            if receipt["result"] == "ambiguous"
        ),
        None,
    )
    if ambiguous is None:
        return None
    return _action_identity(ambiguous)


def resume_report(state: Mapping[str, Any]) -> dict[str, Any]:
    reconciliation: list[dict[str, Any]] = []
    preflight_action = _reconciliation_action(state["preflight"])
    if preflight_action is not None:
        reconciliation.append(
            {
                "action": preflight_action,
                "evidence": None,
                "reasonCode": (
                    "ambiguous-recorded-result"
                    if state["preflight"]["status"] == "reconcile"
                    else "issued-campaign-action"
                ),
            }
        )
    for lane in state["lanes"]:
        action = _reconciliation_action(lane)
        if action is None:
            continue
        checkout = Path(lane["checkoutPath"])
        evidence = _git_evidence(checkout, lane["checkoutDigest"])
        reconciliation.append(
            {
                "action": action,
                "consumer": lane["name"],
                "evidence": evidence,
                "expectedHead": lane["head"],
                "prNumber": lane["prNumber"],
                "reasonCode": (
                    "ambiguous-recorded-result"
                    if lane["status"] == "reconcile"
                    else "issued-action-needs-reconciliation"
                ),
            }
        )
    return {
        "campaignId": state["campaignId"],
        "reconciliation": reconciliation,
        "recoveries": list(state["recoveries"]),
        "release": state["release"],
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "status": state["status"],
    }


def status_report(
    state: Mapping[str, Any], *, show_issued: bool = False
) -> dict[str, Any]:
    plan = None
    if (
        state["preflight"]["status"] == "passed"
        and state["status"] != "complete"
        and not any(lane["status"] == "reconcile" for lane in state["lanes"])
    ):
        plan = _planner(state)
    # Display-only merge-queue transparency (finding #13): a lane waiting at the
    # merge stage that is not the current mergeCandidate is serialized in priority
    # order behind it, not stalled. Surface that so the operator does not misread
    # queue ordering as a stall. This never touches persisted lane["blocker"]
    # (which the transition/relink guards compare against) and never reorders.
    merge_candidate = plan["mergeCandidate"] if plan else None
    lanes = []
    for lane in state["lanes"]:
        held_behind = (
            merge_candidate
            if (
                merge_candidate is not None
                and lane["stage"] == "merge"
                and lane["status"] == "waiting"
                and lane["result"] is None
                and lane["name"] != merge_candidate
            )
            else None
        )
        entry = {
            "attempt": lane["attempt"],
            "blocker": lane["blocker"],
            "cohort": lane["cohort"],
            "head": lane["head"],
            "heldBehind": held_behind,
            "name": lane["name"],
            "nextAction": (
                lane["issuedAction"]["stage"]
                if lane["issuedAction"] is not None
                else lane["stage"]
                if lane["status"] == "waiting"
                else "reconcile"
                if lane["status"] == "reconcile"
                else None
            ),
            "packBlocker": lane["packBlocker"],
            "prNumber": lane["prNumber"],
            "queueNote": (
                f"merge held behind {held_behind} "
                "(lower priority, not yet merged)"
                if held_behind is not None
                else None
            ),
            "receiptCount": len(lane["receipts"]),
            "result": lane["result"],
            "stage": lane["stage"],
            "status": lane["status"],
        }
        if show_issued:
            # Idempotent peek (finding #9): surface the already-issued actionId
            # read-only so an operator can recover it without a mutating `next`.
            issued = lane["issuedAction"]
            entry["issuedActionId"] = issued["actionId"] if issued else None
        lanes.append(entry)
    return {
        "allowParkedCanary": state["allowParkedCanary"],
        "campaignId": state["campaignId"],
        "lanes": lanes,
        "noMerge": state["noMerge"],
        "plan": plan,
        "preflight": {
            "attempt": state["preflight"]["attempt"],
            "receiptCount": len(state["preflight"]["receipts"]),
            "status": state["preflight"]["status"],
        },
        "recoveries": list(state["recoveries"]),
        "release": state["release"],
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "status": state["status"],
    }


def _planning_identity(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "campaignId": state["campaignId"],
        "fleetManifest": state["fleetManifest"],
        "fleetManifestDigest": state["fleetManifestDigest"],
        "lanes": [
            {
                "candidateTimeoutSeconds": lane["candidateTimeoutSeconds"],
                "checkoutDigest": lane["checkoutDigest"],
                "checkoutPath": lane["checkoutPath"],
                "cohort": lane["cohort"],
                "name": lane["name"],
                "priority": lane["priority"],
            }
            for lane in state["lanes"]
        ],
        "allowParkedCanary": state["allowParkedCanary"],
        "manifestConsumers": state["manifestConsumers"],
        "noMerge": state["noMerge"],
        "release": state["release"],
        "repositoryDigest": state["repositoryDigest"],
        "schemaVersion": state["schemaVersion"],
    }


def _render(value: Mapping[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return
    print(f"campaign: {value.get('campaignId', 'unknown')}")
    print(f"release: {value.get('release', 'unknown')}")
    print(f"status: {value.get('status', 'unknown')}")
    for lane in value.get("lanes", []):
        print(
            f"{lane['name']}: {lane['status']} stage={lane['stage']} "
            f"result={lane['result'] or 'none'} next={lane['nextAction'] or 'none'}"
        )


def _load_provenance(path: Path) -> dict[str, Any]:
    """Validate a first-class operator-decision provenance file (finding #9).

    Turns the previously hand-authored, unvalidated JSON convention into a
    checked input: it must be a JSON object carrying a ``reasonCode`` token, which
    becomes the receipt reason code when ``--reason-code`` is not given.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FleetControllerError(f"cannot read provenance file: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FleetControllerError(
            f"provenance file is not valid JSON: {exc}"
        ) from None
    if not isinstance(data, dict):
        raise FleetControllerError("provenance must be a JSON object")
    if "reasonCode" not in data:
        raise FleetControllerError("provenance must include a 'reasonCode'")
    safe_token(data["reasonCode"], "provenance reasonCode")
    return data


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--state-home", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan and resume deterministic fleet refresh campaigns."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan")
    _common(plan)
    plan.add_argument("--release", required=True)
    plan.add_argument("--fleet", type=Path)
    plan.add_argument("--manifest", type=Path)
    plan.add_argument("--consumer", action="append", default=[])
    plan.add_argument("--checkout", action="append", default=[])
    plan.add_argument("--no-merge", action="store_true")
    plan.add_argument(
        "--allow-parked-canary",
        action="store_true",
        help="an operator-decision (parked) canary settles the cohort, not halts it",
    )

    next_parser = commands.add_parser("next")
    _common(next_parser)

    record = commands.add_parser("record")
    _common(record)
    record.add_argument("--release", required=True)
    record.add_argument("--action-id", required=True)
    record.add_argument("--consumer")
    record.add_argument("--result", required=True, choices=sorted(RESULTS))
    record.add_argument("--reason-code")
    record.add_argument("--blocker")
    record.add_argument("--pack-blocker", action="store_true")
    record.add_argument("--head")
    record.add_argument("--pr-number", type=int)
    record.add_argument(
        "--provenance",
        type=Path,
        help=(
            "First-class provenance file (JSON object with a 'reasonCode' token); "
            "required for --result operator-decision"
        ),
    )

    status = commands.add_parser("status")
    _common(status)
    status.add_argument(
        "--show-issued",
        action="store_true",
        help="Include each lane's already-issued actionId (read-only; issues nothing)",
    )

    resume = commands.add_parser("resume")
    _common(resume)
    resume.add_argument("--retry-consumer")
    resume.add_argument("--recover-consumer")
    resume.add_argument("--corrective-release")
    resume.add_argument("--recover-exhausted-consumer")
    resume.add_argument("--exhausted-action")
    resume.add_argument("--decide-consumer")
    resume.add_argument("--decision", choices=sorted(OPERATOR_DECISIONS))
    resume.add_argument("--decided-by")
    resume.add_argument("--decision-head")
    resume.add_argument("--resolve-action")
    resume.add_argument("--release")
    resume.add_argument("--consumer")
    resume.add_argument(
        "--result", choices=sorted(RESULTS - {"ambiguous"})
    )
    resume.add_argument("--reason-code")
    resume.add_argument("--blocker")
    resume.add_argument("--pack-blocker", action="store_true")
    resume.add_argument("--head")
    resume.add_argument("--pr-number", type=int)

    validate = commands.add_parser("validate")
    _common(validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        store = CampaignStore(args.repo, args.campaign, args.state_home)
        if args.command == "plan":
            fleet_path = args.fleet or args.repo / "docs/fleet/consumers.json"
            manifest_path = args.manifest or args.repo / "manifest.json"
            state = new_state(
                repo=args.repo,
                campaign=args.campaign,
                release=args.release,
                fleet_path=fleet_path,
                pack_manifest_path=manifest_path,
                selected=args.consumer,
                checkout_overrides=_checkout_overrides(args.checkout),
                no_merge=args.no_merge,
                allow_parked_canary=args.allow_parked_canary,
            )
            with store.locked():
                if store.state_path.exists():
                    existing = store.load()
                    if _planning_identity(existing) != _planning_identity(state):
                        raise FleetControllerError(
                            "campaign already exists with different identity or policy"
                        )
                    state = existing
                    changed = False
                else:
                    store.write(state)
                    changed = True
            report = status_report(state)
            report["changed"] = changed
            _render(report, args.json)
            return 0

        if args.command == "status":
            _render(
                status_report(store.load(), show_issued=args.show_issued),
                args.json,
            )
            return 0
        if args.command == "validate":
            state = store.load()
            _planner(state)
            _render(
                {
                    "campaignId": state["campaignId"],
                    "release": state["release"],
                    "schemaVersion": REPORT_SCHEMA_VERSION,
                    "status": "valid",
                },
                args.json,
            )
            return 0
        if (
            args.command == "resume"
            and args.retry_consumer is None
            and args.recover_consumer is None
            and args.recover_exhausted_consumer is None
            and args.decide_consumer is None
            and args.resolve_action is None
        ):
            if args.corrective_release is not None:
                raise FleetControllerError(
                    "corrective-release requires recover-consumer"
                )
            if args.exhausted_action is not None:
                raise FleetControllerError(
                    "exhausted-action requires recover-exhausted-consumer"
                )
            if (
                args.decision is not None
                or args.decided_by is not None
                or args.decision_head is not None
            ):
                raise FleetControllerError(
                    "decision, decided-by, and decision-head require decide-consumer"
                )
            _render(resume_report(store.load()), args.json)
            return 0

        with store.locked():
            state = store.load()
            if args.command == "next":
                actions = issue_next(state)
                store.write(state)
                _render(
                    {
                        "actions": actions,
                        "campaignId": state["campaignId"],
                        "release": state["release"],
                        "schemaVersion": REPORT_SCHEMA_VERSION,
                        "status": state["status"],
                    },
                    args.json,
                )
                return 0
            if args.command == "record":
                reason_code = args.reason_code
                if args.result == "operator-decision" and args.provenance is None:
                    raise FleetControllerError(
                        "operator-decision requires --provenance <file>"
                    )
                if args.provenance is not None:
                    provenance = _load_provenance(args.provenance)
                    if reason_code is None:
                        reason_code = provenance["reasonCode"]
                receipt, changed = record_result(
                    state,
                    action_id=args.action_id,
                    release=args.release,
                    consumer=args.consumer,
                    result=args.result,
                    reason_code=reason_code,
                    blocker=args.blocker,
                    pack_blocker=args.pack_blocker,
                    head=args.head,
                    pr_number=args.pr_number,
                )
                if changed:
                    store.write(state)
                _render(
                    {
                        "campaignId": state["campaignId"],
                        "changed": changed,
                        "receipt": receipt,
                        "release": state["release"],
                        "schemaVersion": REPORT_SCHEMA_VERSION,
                        "status": state["status"],
                    },
                    args.json,
                )
                return 0
            if args.command == "resume":
                resume_receipt: dict[str, Any] | None
                recovery: dict[str, Any] | None = None
                changed = True
                modes = sum(
                    item is not None
                    for item in (
                        args.retry_consumer,
                        args.recover_consumer,
                        args.recover_exhausted_consumer,
                        args.decide_consumer,
                        args.resolve_action,
                    )
                )
                if modes > 1:
                    raise FleetControllerError(
                        "resume accepts only one recovery mode"
                    )
                if args.decide_consumer is None and (
                    args.decision is not None
                    or args.decided_by is not None
                    or args.decision_head is not None
                ):
                    raise FleetControllerError(
                        "decision, decided-by, and decision-head are valid only "
                        "with decide-consumer"
                    )
                if args.retry_consumer is not None:
                    if args.corrective_release is not None:
                        raise FleetControllerError(
                            "corrective-release is valid only with recover-consumer"
                        )
                    if args.exhausted_action is not None:
                        raise FleetControllerError(
                            "exhausted-action is valid only with recover-exhausted-consumer"
                        )
                    retry_consumer(state, args.retry_consumer)
                    resume_receipt = None
                elif args.recover_consumer is not None:
                    if args.corrective_release is None:
                        raise FleetControllerError(
                            "recover-consumer requires corrective-release"
                        )
                    if args.exhausted_action is not None:
                        raise FleetControllerError(
                            "exhausted-action is valid only with recover-exhausted-consumer"
                        )
                    recovery, changed = recover_pack_blocker(
                        state,
                        consumer=args.recover_consumer,
                        corrective_release=args.corrective_release,
                        actual_release=_pack_release(args.repo / "manifest.json"),
                    )
                    resume_receipt = None
                elif args.recover_exhausted_consumer is not None:
                    if args.corrective_release is not None:
                        raise FleetControllerError(
                            "corrective-release is valid only with recover-consumer"
                        )
                    if args.exhausted_action is None:
                        raise FleetControllerError(
                            "recover-exhausted-consumer requires exhausted-action"
                        )
                    if args.release is None:
                        raise FleetControllerError(
                            "recover-exhausted-consumer requires release"
                        )
                    recovery, changed = recover_retry_exhausted(
                        state,
                        consumer=args.recover_exhausted_consumer,
                        exhausted_action_id=args.exhausted_action,
                        release=args.release,
                    )
                    resume_receipt = None
                elif args.decide_consumer is not None:
                    if args.corrective_release is not None:
                        raise FleetControllerError(
                            "corrective-release is valid only with recover-consumer"
                        )
                    if args.exhausted_action is not None:
                        raise FleetControllerError(
                            "exhausted-action is valid only with recover-exhausted-consumer"
                        )
                    if (
                        args.decision is None
                        or args.decided_by is None
                        or args.decision_head is None
                    ):
                        raise FleetControllerError(
                            "decide-consumer requires decision, decided-by, "
                            "and decision-head"
                        )
                    if args.release is None:
                        raise FleetControllerError("decide-consumer requires release")
                    recovery, changed = record_operator_decision(
                        state,
                        consumer=args.decide_consumer,
                        decision=args.decision,
                        decided_by=args.decided_by,
                        decision_head=args.decision_head,
                        release=args.release,
                    )
                    resume_receipt = None
                else:
                    if args.corrective_release is not None:
                        raise FleetControllerError(
                            "corrective-release is valid only with recover-consumer"
                        )
                    if args.exhausted_action is not None:
                        raise FleetControllerError(
                            "exhausted-action is valid only with recover-exhausted-consumer"
                        )
                    if args.release is None or args.result is None:
                        raise FleetControllerError(
                            "resolve-action requires release and result"
                        )
                    resume_receipt, _changed = resolve_reconciliation(
                        state,
                        action_id=args.resolve_action,
                        release=args.release,
                        consumer=args.consumer,
                        result=args.result,
                        reason_code=args.reason_code,
                        blocker=args.blocker,
                        pack_blocker=args.pack_blocker,
                        head=args.head,
                        pr_number=args.pr_number,
                    )
                if changed:
                    store.write(state)
                report = resume_report(state)
                report["receipt"] = resume_receipt
                if recovery is not None:
                    report["recovery"] = recovery
                    report["changed"] = changed
                _render(report, args.json)
                return 0
    except (FleetControllerError, fleet_lib.FleetConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        detail = error.strerror or type(error).__name__
        print(f"error: filesystem operation failed: {detail}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
