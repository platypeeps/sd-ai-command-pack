#!/usr/bin/env python3
"""Plan and execute the exact-scope local stage consumed by ``sd-review``."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    Literal,
    Mapping,
    MutableMapping,
    NoReturn,
    Sequence,
    overload,
)
from urllib.parse import urlsplit

from sd_ai_command_pack_lib import (
    REVIEW_FINDING_FAMILY_IDS,
    CacheSetupError,
    build_tool_environment,
    declare_verdict_domain,
    run_git_minimal,
)

SCHEMA_VERSION = 1
CONFIG_PATH = Path(".sd-ai-command-pack/review.json")
DEFAULT_ARTIFACT_ROOT = Path(".build/sd-review")
MAX_CONFIG_BYTES = 256 * 1024
MAX_PROVIDERS = 16
MAX_PATHS = 20_000
MAX_ARGV = 64
MAX_ARG_LENGTH = 4096
MAX_EXPANDED_ARGV_BYTES = 128 * 1024
MAX_FINDINGS = 1_000
# A caller-supplied miscitation line is bounded so a receipt cannot record an
# arbitrarily large integer for a location nobody can reach in a real file.
MAX_CITATION_LINE = 10_000_000
# Matches the miscited path bound. An accepted reason is free text a human
# will read out of the receipt while auditing a waiver, so it is bounded for
# the reader's sake rather than the parser's.
MAX_ACCEPTED_REASON = 500
ASCII_DIGITS = frozenset("0123456789")
MAX_FAMILY_AUDITS = 32
MAX_FAMILY_EXTENSIONS = 32
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_TIMEOUT = 3600
GIT_TIMEOUT_SECONDS = 60
ID_RE = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
ATTEMPT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
SCOPES = frozenset({"changes", "branch", "codebase", "pr"})
CANONICAL_SCOPES = frozenset({"worktree", "branch_delta", "codebase"})
DATA_CLASSES = ("local", "private-network", "public-network")
COST_TIERS = ("none", "low", "medium", "high")
QUALITY_TIERS = ("basic", "standard", "deep")
SHELL_EXECUTABLES = frozenset({"bash", "dash", "fish", "ksh", "sh", "zsh"})
CODE_STRING_EXECUTABLES = frozenset(
    {"node", "nodejs", "perl", "python", "python3", "ruby"}
)
# The local review verdict vocabulary as an explicit extension of the shared
# core (A-077): ``clean``/``failed``/``skipped`` are core; ``findings``,
# ``unavailable`` and ``cancelled`` are this domain's declared opt-outs.
OUTCOMES = declare_verdict_domain(
    "review-local",
    {"clean", "findings", "unavailable", "failed", "cancelled", "skipped"},
    opt_out={"findings", "unavailable", "cancelled"},
)
TERMINAL_FAILURES = frozenset({"unavailable", "failed", "cancelled"})
FINDING_SEVERITY_RANK = {"unspecified": 0, "low": 1, "medium": 2, "high": 3}
CODEX_SCHEMA_FILE = "codex-schema.json"
CODEX_ANSWER_FILE = "codex-answer.json"
CODEX_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "maxItems": 50,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "line", "severity", "summary", "family"],
                "properties": {
                    "path": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "severity": {"enum": ["high", "medium", "low", "unspecified"]},
                    "summary": {"type": "string"},
                    "family": {"type": "string"},
                },
            },
        }
    },
}


def codex_instruction_surfaces(paths: Sequence[str]) -> list[str]:
    """Reviewed paths that codex itself would load as instructions.

    codex discovers skills under ``.agents/skills`` and ``.codex/skills`` in
    the directory it runs in, and every discovered skill's name and
    description enter the model's context whether or not the skill is
    invoked. A change that adds or edits one is therefore writing text into
    the context of the lane reviewing it, which is exactly the influence an
    independent gate must not grant. ``AGENTS.md`` is excluded: the lane
    already runs with ``project_doc_max_bytes=0``.
    """
    tainted = []
    for path in paths:
        lowered = path.lower()
        parts = lowered.split("/")
        if parts[0] == ".codex":
            tainted.append(path)
        elif parts[-1] == "skill.md" and "skills" in parts[:-1]:
            tainted.append(path)
    return sorted(tainted)


def _codex_prompt(scope: str, base: str, head: str) -> str:
    """Prompt for codex exec. Codex fetches the diff itself from the exact
    refs the coordinator resolved, so the argv stays small."""
    if scope == "branch_delta":
        subject = (
            f"the committed change `git diff {base}..{head}`; do not review the "
            "working tree beyond those two refs"
        )
    else:
        subject = (
            "the uncommitted working-tree change: `git diff HEAD` plus every "
            "file listed by `git status --porcelain --untracked-files=all`"
        )
    return (
        "You are one lane of a multi-provider code review gate, taking the "
        "adversarial stance: find the strongest reasons this change should not "
        f"ship yet. Review {subject}. Report defects the change introduces: "
        "correctness bugs, security issues, data-integrity risks, and "
        "maintainability problems that would cost real time later. Judge "
        "severity per finding; high means it should block a merge. Do not "
        "report style, wording, or observations that are not defects, and "
        "prefer few precise findings over many speculative ones. path is the "
        "repository-relative file, line is the line in the new version or "
        "null, family is one short category word such as security, "
        "correctness, testing, or maintainability. Respond only with JSON "
        "matching the output schema; an empty findings array means clean."
    )
FINDING_FAMILY_IDS = REVIEW_FINDING_FAMILY_IDS
FINDING_DISPOSITIONS = frozenset(
    {"outstanding", "fix", "fixed", "rebutted", "resolved", "miscited"}
)
# The caller-supplied disposition vocabulary. ``rebutted`` records a verified
# judgement that a reported finding is not real; ``miscited`` records that the
# finding may describe something real but does not describe the code at the
# location it names, and so carries a citation the caller checked. ``accepted``
# is the third ground and the only one that concedes the finding: the claim is
# true, the repository has decided against acting on it, and the caller signs
# for that with a required reason. None of the three ever deletes the finding.
#
# ``accepted`` deliberately does NOT join ``FINDING_DISPOSITIONS``. That set has
# one use -- ``_parse_family_finding`` -- and validates ``--family-evidence``
# payloads, a different input path with no defined meaning for a waiver.
LOCAL_DISPOSITION_VALUES = frozenset({"rebutted", "miscited", "accepted"})
FAMILY_AUDIT_DIMENSIONS = {
    "task-metadata": (
        "identity-fields",
        "lifecycle-status",
        "parent-child-links",
        "branch-base-binding",
        "archive-journal-bundle",
    ),
    "boundary-validation": (
        "strict-types",
        "normalization",
        "persistence-invariants",
        "state-transitions",
        "replay-idempotency",
        "attempts-receipts",
        "exact-identity-head",
        "subprocess-failures",
        "permissions",
        "paths-symlinks-toctou",
        "controlled-diagnostics",
    ),
    "contract-documentation-drift": (
        "typed-contract",
        "human-output",
        "json-output",
        "help-documentation",
        "generated-adapters",
    ),
    "generated-surfaces": (
        "canonical-source",
        "generated-mirrors",
        "manifest-registration",
        "install-audit",
        "release-evidence",
    ),
    "reviewer-test-harness-quality": (
        "good-fixture",
        "base-fixture",
        "failure-fixture",
        "mutation-sentinel",
        "non-tautological-assertion",
    ),
    "other": (
        "root-cause",
        "sibling-paths",
        "sibling-transitions",
        "failure-branches",
        "generated-surfaces",
    ),
}
ACTIVE_PROCESSES: set[subprocess.Popen[bytes]] = set()
ACTIVE_PROCESSES_LOCK = threading.Lock()
CANCELLATION_EVENT = threading.Event()
CONFIG_KEYS = frozenset(
    {"schemaVersion", "providers", "policy", "remoteIntegration"}
)
PROVIDER_KEYS = frozenset(
    {
        "id",
        "adapter",
        "argv",
        "scopes",
        "dataHandling",
        "costTier",
        "qualityTier",
        "timeoutSeconds",
        "version",
        "enabled",
        "outcomeByExitCode",
        "requiresTreeAtHead",
    }
)
POLICY_KEYS = frozenset(
    {
        "allowedDataHandling",
        "documentation",
        "metadata",
        "requiredProviders",
        "localAdvisorySeverityCeiling",
    }
)
# Severities a repository may declare advisory. Deliberately excludes "high"
# -- accepting it would let a policy author lower the blocking floor to
# nothing -- and "unspecified", whose rank 0 means the provider told us
# nothing, which is the last classification that should open a gate.
ADVISORY_CEILING_VALUES = ("low", "medium")
REMOTE_INTEGRATION_KEYS = frozenset(
    {
        "requirement",
        "descriptorPath",
        "receiptPolls",
        "pollSeconds",
        "roundLimit",
    }
)
SUBSTANTIVE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".mjs",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".sh",
        ".sql",
        ".swift",
        ".ts",
        ".tsx",
    }
)
DOCUMENT_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})
METADATA_NAMES = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        "changelog.md",
        "license",
        "license.md",
        "manifest.json",
    }
)


class ReviewInputError(ValueError):
    """A controlled invalid target, policy, or receipt condition."""


@dataclass(frozen=True)
class Provider:
    identifier: str
    adapter: str
    argv: tuple[str, ...]
    scopes: tuple[str, ...]
    data_handling: str
    cost_tier: str
    quality_tier: str
    timeout_seconds: int
    version: str
    enabled: bool
    outcome_by_exit: Mapping[int, str]
    # True when the provider reads file *content* from the working tree rather
    # than from the refs it is given. Such a provider cannot honour a head the
    # tree does not hold: it would review the requested range's diff against
    # whatever is checked out. Declared, not inferred from the adapter at the
    # call site, so an argv provider wrapping such a tool can opt in.
    requires_tree_at_head: bool = False


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _bounded(value: str, limit: int = 1200) -> str:
    text = " ".join(value.replace("\x00", " ").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _default_config() -> dict[str, Any]:
    shared = {
        "scopes": ["worktree", "branch_delta", "codebase"],
        "dataHandling": "private-network",
        "qualityTier": "standard",
        "enabled": True,
    }
    return {
        "schemaVersion": 1,
        "providers": [
            {
                **shared,
                "id": "codex",
                "adapter": "codex",
                "argv": [],
                "scopes": ["worktree", "branch_delta"],
                "costTier": "none",
                "qualityTier": "deep",
                "timeoutSeconds": 900,
                "version": "builtin-v1",
                "outcomeByExitCode": {
                    "0": "clean",
                    "1": "unavailable",
                    "2": "unavailable",
                },
            },
            {
                **shared,
                "id": "prism",
                "adapter": "prism",
                "argv": [],
                "costTier": "low",
                "timeoutSeconds": 300,
                "version": "builtin-v1",
                "outcomeByExitCode": {
                    "0": "clean",
                    "1": "findings",
                    "3": "unavailable",
                    "4": "unavailable",
                },
            },
            {
                **shared,
                "id": "gito",
                "adapter": "gito",
                "argv": [],
                "costTier": "medium",
                "timeoutSeconds": 600,
                "version": "builtin-v1",
                "outcomeByExitCode": {
                    "0": "clean",
                    "1": "findings",
                    "2": "unavailable",
                    "3": "unavailable",
                },
            },
        ],
        "policy": {
            "allowedDataHandling": list(DATA_CLASSES),
            "documentation": "cheapest",
            "metadata": "cheapest",
            "requiredProviders": [],
        },
        "remoteIntegration": {
            "requirement": "optional",
            "descriptorPath": "config/routed-review-setup-v1.json",
            "receiptPolls": 6,
            "pollSeconds": 5,
            "roundLimit": 5,
        },
    }


def _bounded_integer(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReviewInputError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ReviewInputError(f"{field} must be between {minimum} and {maximum}")
    return value


def _safe_config_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ReviewInputError(f"{field} must be a bounded relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(not part for part in path.parts)
        or re.match(r"[A-Za-z]:", normalized)
        or normalized.startswith("//")
    ):
        raise ReviewInputError(f"{field} must stay inside the repository")
    return path.as_posix()


def _parse_remote_integration(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - REMOTE_INTEGRATION_KEYS:
        raise ReviewInputError("remoteIntegration must use only supported fields")
    requirement = value.get("requirement", "optional")
    if requirement not in {"optional", "required"}:
        raise ReviewInputError(
            "remoteIntegration requirement must be optional or required"
        )
    return {
        "requirement": requirement,
        "descriptorPath": _safe_config_path(
            value.get("descriptorPath", "config/routed-review-setup-v1.json"),
            field="remoteIntegration descriptorPath",
        ),
        "receiptPolls": _bounded_integer(
            value.get("receiptPolls", 6),
            field="remoteIntegration receiptPolls",
            minimum=1,
            maximum=30,
        ),
        "pollSeconds": _bounded_integer(
            value.get("pollSeconds", 5),
            field="remoteIntegration pollSeconds",
            minimum=0,
            maximum=60,
        ),
        "roundLimit": _bounded_integer(
            value.get("roundLimit", 5),
            field="remoteIntegration roundLimit",
            minimum=1,
            maximum=10,
        ),
    }


def _read_json(path: Path, *, limit: int, label: str) -> object:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ReviewInputError(f"cannot inspect {label} {path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ReviewInputError(f"{label} must be a regular non-symlink file: {path}")
    if metadata.st_size > limit:
        raise ReviewInputError(f"{label} exceeds {limit} bytes: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewInputError(f"cannot read {label} {path}: {error}") from error
    return value


def _string_list(
    value: object, *, field: str, allowed: set[str] | None = None
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item or len(item) > MAX_ARG_LENGTH
        for item in value
    ):
        raise ReviewInputError(f"{field} must be a bounded string array")
    items = tuple(value)
    if allowed is not None and any(item not in allowed for item in items):
        raise ReviewInputError(f"{field} contains an unsupported value")
    if len(items) > MAX_ARGV:
        raise ReviewInputError(f"{field} exceeds {MAX_ARGV} entries")
    return items


def _parse_provider(value: object) -> Provider:
    if not isinstance(value, dict) or set(value) - PROVIDER_KEYS:
        raise ReviewInputError("provider entries must use only supported fields")
    identifier = value.get("id")
    adapter = value.get("adapter")
    version = value.get("version")
    if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier):
        raise ReviewInputError("provider id is invalid")
    if adapter not in {"prism", "gito", "codex", "argv"}:
        raise ReviewInputError(f"provider {identifier} has an unsupported adapter")
    if not isinstance(version, str) or not version or len(version) > 128:
        raise ReviewInputError(f"provider {identifier} version is invalid")
    argv = _string_list(value.get("argv", []), field=f"provider {identifier} argv")
    if adapter == "argv" and not argv:
        raise ReviewInputError(f"provider {identifier} argv adapter requires argv")
    if adapter != "argv" and argv:
        raise ReviewInputError(
            f"provider {identifier} builtin adapter cannot override argv"
        )
    if any("\x00" in item for item in argv):
        raise ReviewInputError(f"provider {identifier} argv contains a NUL byte")
    executable = PurePosixPath(argv[0]).name.casefold() if argv else ""
    if executable in SHELL_EXECUTABLES and any(
        item in {"-c", "-lc"} for item in argv[1:]
    ):
        raise ReviewInputError(
            f"provider {identifier} cannot use a shell command string"
        )
    if executable in CODE_STRING_EXECUTABLES and any(
        item in {"-c", "-e", "--eval"} for item in argv[1:]
    ):
        raise ReviewInputError(
            f"provider {identifier} cannot use an inline code string"
        )
    scopes = _string_list(
        value.get("scopes"),
        field=f"provider {identifier} scopes",
        allowed=set(CANONICAL_SCOPES),
    )
    if not scopes:
        raise ReviewInputError(f"provider {identifier} scopes cannot be empty")
    data_handling = value.get("dataHandling")
    cost_tier = value.get("costTier")
    quality_tier = value.get("qualityTier")
    if data_handling not in DATA_CLASSES:
        raise ReviewInputError(f"provider {identifier} dataHandling is invalid")
    if cost_tier not in COST_TIERS:
        raise ReviewInputError(f"provider {identifier} costTier is invalid")
    if quality_tier not in QUALITY_TIERS:
        raise ReviewInputError(f"provider {identifier} qualityTier is invalid")
    timeout = value.get("timeoutSeconds")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not 1 <= timeout <= MAX_TIMEOUT
    ):
        raise ReviewInputError(f"provider {identifier} timeoutSeconds is invalid")
    enabled = value.get("enabled")
    if not isinstance(enabled, bool):
        raise ReviewInputError(f"provider {identifier} enabled must be boolean")
    requires_tree_at_head = value.get("requiresTreeAtHead")
    if requires_tree_at_head is None:
        # gito resolves the diff from refs but reads content from the tree;
        # codex runs inside the checkout and reads whatever is there.
        requires_tree_at_head = adapter in {"gito", "codex"}
    elif adapter != "argv":
        raise ReviewInputError(
            f"provider {identifier} builtin adapter cannot override requiresTreeAtHead"
        )
    elif not isinstance(requires_tree_at_head, bool):
        raise ReviewInputError(
            f"provider {identifier} requiresTreeAtHead must be boolean"
        )
    raw_exit = value.get("outcomeByExitCode")
    if not isinstance(raw_exit, dict) or len(raw_exit) > 32:
        raise ReviewInputError(f"provider {identifier} outcomeByExitCode is invalid")
    exit_map: dict[int, str] = {}
    for key, outcome in raw_exit.items():
        try:
            code = int(key)
        except (TypeError, ValueError):
            raise ReviewInputError(
                f"provider {identifier} outcomeByExitCode key is invalid"
            ) from None
        if str(code) != str(key) or code < 0 or code > 255 or outcome not in OUTCOMES:
            raise ReviewInputError(f"provider {identifier} exit mapping is invalid")
        exit_map[code] = str(outcome)
    if 0 not in exit_map:
        raise ReviewInputError(f"provider {identifier} must map exit code 0")
    return Provider(
        identifier,
        str(adapter),
        argv,
        scopes,
        str(data_handling),
        str(cost_tier),
        str(quality_tier),
        timeout,
        version,
        enabled,
        exit_map,
        bool(requires_tree_at_head),
    )


def load_config(
    repo: Path,
) -> tuple[dict[str, Any], tuple[Provider, ...], dict[str, Any]]:
    path = repo / CONFIG_PATH
    value = (
        _read_json(path, limit=MAX_CONFIG_BYTES, label="review configuration")
        if path.exists()
        else _default_config()
    )
    if not isinstance(value, dict) or set(value) - CONFIG_KEYS:
        raise ReviewInputError("review configuration must use only supported fields")
    if value.get("schemaVersion") != SCHEMA_VERSION:
        raise ReviewInputError("review configuration schemaVersion must be 1")
    raw_providers = value.get("providers")
    if (
        not isinstance(raw_providers, list)
        or not 1 <= len(raw_providers) <= MAX_PROVIDERS
    ):
        raise ReviewInputError(
            "review configuration providers must be a bounded non-empty array"
        )
    providers = tuple(_parse_provider(item) for item in raw_providers)
    identifiers = [item.identifier for item in providers]
    if len(set(identifiers)) != len(identifiers):
        raise ReviewInputError("review provider ids must be unique")
    policy = value.get("policy")
    if not isinstance(policy, dict) or set(policy) - POLICY_KEYS:
        raise ReviewInputError("review policy must use only supported fields")
    allowed = _string_list(
        policy.get("allowedDataHandling"),
        field="policy allowedDataHandling",
        allowed=set(DATA_CLASSES),
    )
    if not allowed:
        raise ReviewInputError("policy allowedDataHandling cannot be empty")
    for field in ("documentation", "metadata"):
        if policy.get(field) not in {"cheapest", "skip"}:
            raise ReviewInputError(f"policy {field} must be cheapest or skip")
    required = _string_list(
        policy.get("requiredProviders"), field="policy requiredProviders"
    )
    unknown = sorted(set(required) - set(identifiers))
    if unknown:
        raise ReviewInputError(
            f"policy requiredProviders contains unknown provider {unknown[0]}"
        )
    ceiling = policy.get("localAdvisorySeverityCeiling")
    if ceiling is not None and ceiling not in ADVISORY_CEILING_VALUES:
        raise ReviewInputError(
            "policy localAdvisorySeverityCeiling must be "
            + " or ".join(ADVISORY_CEILING_VALUES)
        )
    normalized_policy = {
        **policy,
        "allowedDataHandling": list(allowed),
        "requiredProviders": list(required),
    }
    normalized_remote = _parse_remote_integration(
        value.get("remoteIntegration", {})
    )
    normalized = {
        "schemaVersion": 1,
        "providers": raw_providers,
        "policy": normalized_policy,
        "remoteIntegration": normalized_remote,
    }
    return normalized, providers, normalized_policy


@overload
def _git(repo: Path, *args: str, binary: Literal[False] = False) -> str: ...


@overload
def _git(repo: Path, *args: str, binary: Literal[True]) -> bytes: ...


def _git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        result = run_git_minimal(
            list(args),
            cwd=repo,
            timeout=GIT_TIMEOUT_SECONDS,
            binary=binary,
        )
    except subprocess.TimeoutExpired as error:
        stderr_value = error.stderr
        stderr_text = (
            stderr_value.decode("utf-8", "replace")
            if isinstance(stderr_value, bytes)
            else stderr_value
        )
        raise ReviewInputError(
            _bounded(
                stderr_text
                or f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS}s"
            )
        ) from error
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace") if binary else result.stderr
        raise ReviewInputError(
            _bounded(stderr or f"git {' '.join(args)} exited {result.returncode}")
        )
    return result.stdout


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ReviewInputError("Git returned an unsafe review path")
    return str(path)


def _nul_paths(payload: bytes) -> list[str]:
    values = payload.split(b"\0")
    if values and values[-1] == b"":
        values.pop()
    if len(values) > MAX_PATHS:
        raise ReviewInputError(f"review target exceeds {MAX_PATHS} paths")
    return sorted({_safe_relative(os.fsdecode(item)) for item in values})


def _path_manifest(repo: Path, paths: Sequence[str]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for value in paths:
        path = repo / value
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            manifest.append({"path": value, "kind": "deleted", "digest": None})
            continue
        if stat.S_ISLNK(metadata.st_mode):
            payload = os.fsencode(os.readlink(path))
            kind = "symlink"
        elif stat.S_ISREG(metadata.st_mode):
            payload = path.read_bytes()
            kind = "file"
        else:
            raise ReviewInputError(
                f"review path is not a regular file or symlink: {value}"
            )
        manifest.append(
            {"path": value, "kind": kind, "digest": hashlib.sha256(payload).hexdigest()}
        )
    return manifest


def _repository_identity(repo: Path) -> str:
    remotes = str(_git(repo, "remote")).splitlines()
    if "origin" not in remotes:
        return f"local:{hashlib.sha256(os.fsencode(str(repo))).hexdigest()}"
    remote = str(_git(repo, "remote", "get-url", "origin")).strip()
    scp_match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", remote)
    if scp_match and "://" not in remote:
        host, remote_path = scp_match.groups()
    else:
        parsed = urlsplit(remote)
        if not parsed.hostname:
            return f"remote:{hashlib.sha256(remote.encode()).hexdigest()}"
        host, remote_path = parsed.hostname, parsed.path
    if (
        len(host) == 1
        or "/" in host
        or "\\" in host
        or "\\" in remote_path
        or any(character.isspace() or ord(character) < 32 for character in host)
    ):
        return f"remote:{hashlib.sha256(remote.encode()).hexdigest()}"
    normalized_path = remote_path.strip("/")
    if normalized_path.endswith(".git"):
        normalized_path = normalized_path[:-4]
    raw_parts = normalized_path.split("/")
    if not normalized_path or any(part in {"", ".", ".."} for part in raw_parts):
        return f"remote:{hashlib.sha256(remote.encode()).hexdigest()}"
    return f"{host.casefold()}/{normalized_path}"


def resolve_target(repo: Path, scope: str, base: str, head: str) -> dict[str, Any]:
    head_oid = str(
        _git(repo, "rev-parse", "--verify", "--end-of-options", f"{head}^{{commit}}")
    ).strip()
    dirty = str(_git(repo, "status", "--porcelain=v1", "--untracked-files=all"))
    if scope in {"branch", "pr"}:
        if dirty:
            raise ReviewInputError(
                f"{scope} scope requires a clean worktree bound to one head"
            )
        base_oid = str(_git(repo, "merge-base", "--", base, head_oid)).strip()
        diff = bytes(
            _git(
                repo,
                "diff",
                "--binary",
                "--full-index",
                f"{base_oid}..{head_oid}",
                "--",
                binary=True,
            )
        )
        paths = _nul_paths(
            bytes(
                _git(
                    repo,
                    "diff",
                    "--name-only",
                    "-z",
                    f"{base_oid}..{head_oid}",
                    "--",
                    binary=True,
                )
            )
        )
        canonical_scope = "branch_delta"
        manifest = _path_manifest(repo, paths)
    elif scope == "changes":
        base_oid = head_oid
        unstaged = bytes(
            _git(repo, "diff", "--binary", "--full-index", "--", binary=True)
        )
        staged = bytes(
            _git(
                repo, "diff", "--cached", "--binary", "--full-index", "--", binary=True
            )
        )
        untracked = _nul_paths(
            bytes(
                _git(
                    repo,
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                    binary=True,
                )
            )
        )
        tracked = _nul_paths(
            bytes(_git(repo, "diff", "--name-only", "-z", "HEAD", "--", binary=True))
        )
        paths = sorted(set(tracked + untracked))
        manifest = _path_manifest(repo, paths)
        diff = (
            unstaged
            + b"\0STAGED\0"
            + staged
            + b"\0UNTRACKED\0"
            + _canonical_json(manifest)
        )
        canonical_scope = "worktree"
    else:
        if dirty:
            raise ReviewInputError(
                "codebase scope requires a clean worktree bound to one head"
            )
        base_oid = head_oid
        paths = _nul_paths(bytes(_git(repo, "ls-files", "-z", binary=True)))
        manifest = _path_manifest(repo, paths)
        diff = _canonical_json(manifest)
        canonical_scope = "codebase"
    target = {
        "repository": _repository_identity(repo),
        "scope": canonical_scope,
        "base": base_oid,
        "head": head_oid,
        "paths": manifest,
        "contentDigest": hashlib.sha256(diff).hexdigest(),
    }
    target["identity"] = _digest(target)
    return target


def classify_paths(paths: Sequence[str]) -> tuple[str, list[str]]:
    if not paths:
        return "metadata", ["empty-delta"]
    reasons: set[str] = set()
    only_docs = True
    only_metadata = True
    for value in paths:
        path = PurePosixPath(value)
        lowered = value.casefold()
        suffix = path.suffix.casefold()
        name = path.name.casefold()
        is_doc = suffix in DOCUMENT_SUFFIXES or lowered.startswith("docs/")
        is_metadata = (
            is_doc or name in METADATA_NAMES or lowered.startswith(".trellis/")
        )
        only_docs = only_docs and is_doc
        only_metadata = only_metadata and is_metadata
        if suffix in SUBSTANTIVE_SUFFIXES:
            reasons.add("source")
        if (
            bool({"test", "tests"} & set(path.parts))
            or name.startswith("test_")
            or name.endswith("_test.py")
        ):
            reasons.add("tests")
        if lowered.startswith((".github/workflows/", "scripts/", "installer/")):
            reasons.add("executable-configuration")
        if any(
            token in lowered
            for token in ("security", "auth", "receipt", "state", "contract")
        ):
            reasons.add("state-contract")
    if only_docs:
        return "documentation", ["documentation-only"]
    if only_metadata:
        return "metadata", ["metadata-only"]
    return "substantive", sorted(reasons or {"ambiguous"})


def _provider_row(provider: Provider) -> dict[str, Any]:
    return {
        "id": provider.identifier,
        "adapter": provider.adapter,
        "version": provider.version,
        "dataHandling": provider.data_handling,
        "costTier": provider.cost_tier,
        "qualityTier": provider.quality_tier,
        "timeoutSeconds": provider.timeout_seconds,
    }


# Every `--bookkeeping-evidence` rejection ends with this. The flag's contract
# was previously discoverable only by reading the function below, and a caller
# who reverse-engineers a schema from source is one step from hand-authoring a
# payload to satisfy the check -- which is manufacturing the very evidence the
# classification exists to require. So the message names the shape, names the
# artifact it is confused with, and names the one honest way to obtain the
# three target values: this command's own `--plan-only` report, which derives
# them from the repository. What it deliberately does NOT do is print the
# target's own `base`, `head`, or `contentDigest` in the rejection -- handing
# over the expected values is the same shortcut in a friendlier costume,
# because a pasted value proves nothing about the tree it claims to describe.
BOOKKEEPING_EVIDENCE_SHAPE = (
    "--bookkeeping-evidence expects a JSON file holding an object with exactly "
    '"schemaVersion": 1, "classification": "bookkeeping-successor", and '
    '"base", "head", "contentDigest" equal to the reviewed target. It is not '
    "the final-bundle finish-work receipt, a different artifact that shares "
    "the word bookkeeping. Obtain the three target values from the "
    '"target" object in this command\'s own --plan-only --json report for the '
    "same --repo, --base, and --head; see the successor-head re-entry section "
    "of the sd-review skill."
)


def _bookkeeping_evidence_path(value: str | None) -> Path | None:
    """Resolve the flag, attributing a filesystem failure to the flag.

    `Path(...).resolve(strict=True)` raises `OSError`, which the caller's
    blanket `except (OSError, ReviewInputError)` stringifies verbatim: the
    operator sees `[Errno 2] No such file or directory: '<path>'` and is told
    neither which argument was at fault nor that a JSON receipt was wanted.
    Resolving here rather than widening that `except` keeps the attribution
    with the one flag that needs it.
    """

    if not value:
        return None
    try:
        return Path(value).resolve(strict=True)
    except OSError as error:
        raise ReviewInputError(
            f"cannot read --bookkeeping-evidence {_bounded(value, 300)}: "
            f"{error.strerror or error}. {BOOKKEEPING_EVIDENCE_SHAPE}"
        ) from error


def _validate_bookkeeping_evidence(
    path: Path | None, target: Mapping[str, Any]
) -> None:
    if path is None:
        raise ReviewInputError(
            f"bookkeeping successor requires --bookkeeping-evidence. "
            f"{BOOKKEEPING_EVIDENCE_SHAPE}"
        )
    # `_read_json` already attributes its own failures, but with a bare label:
    # "cannot read bookkeeping evidence <path>: Expecting value". The label is
    # the flag spelling so the reader knows which argument to fix, and the
    # shape is appended so a size, encoding, or parse rejection carries the
    # same contract every other branch here carries.
    try:
        value = _read_json(path, limit=64 * 1024, label="--bookkeeping-evidence")
    except ReviewInputError as error:
        raise ReviewInputError(f"{error}. {BOOKKEEPING_EVIDENCE_SHAPE}") from error
    if not isinstance(value, dict):
        raise ReviewInputError(
            f"bookkeeping evidence must be a JSON object. "
            f"{BOOKKEEPING_EVIDENCE_SHAPE}"
        )
    if value.get("schemaVersion") != 1:
        raise ReviewInputError(
            f"bookkeeping evidence schemaVersion must be 1. "
            f"{BOOKKEEPING_EVIDENCE_SHAPE}"
        )
    required = {"base", "head", "contentDigest", "classification"}
    allowed = required | {"schemaVersion"}
    if set(value) != allowed:
        missing = sorted(allowed - set(value))
        unsupported = sorted(set(value) - allowed)
        detail = ", ".join(
            part
            for part in (
                f"missing {', '.join(missing)}" if missing else "",
                f"unsupported {', '.join(unsupported)}" if unsupported else "",
            )
            if part
        )
        raise ReviewInputError(
            f"bookkeeping evidence has unsupported or missing fields "
            f"({_bounded(detail, 300)}). {BOOKKEEPING_EVIDENCE_SHAPE}"
        )
    if value.get("classification") != "bookkeeping-successor":
        raise ReviewInputError(
            f"bookkeeping evidence classification must be "
            f'"bookkeeping-successor". {BOOKKEEPING_EVIDENCE_SHAPE}'
        )
    # Name the field that disagreed, never the value the target holds. The
    # supplied value is echoed through `_bounded` because it is the
    # caller-controlled half; the expected one stays unsaid.
    disagreed = [
        key
        for key in ("base", "head", "contentDigest")
        if value.get(key) != target.get(key)
    ]
    if disagreed:
        supplied = ", ".join(
            f"{key}={_bounded(str(value.get(key)), 100)}" for key in disagreed
        )
        raise ReviewInputError(
            f"bookkeeping evidence does not match the exact target: "
            f"{', '.join(disagreed)} "
            f"{'disagree' if len(disagreed) > 1 else 'disagrees'} "
            f"(supplied {_bounded(supplied, 400)}). "
            f"{BOOKKEEPING_EVIDENCE_SHAPE}"
        )


def _family_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or value not in FINDING_FAMILY_IDS:
        raise ReviewInputError(f"{field} must use the bounded finding-family vocabulary")
    return value


def _safe_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not ATTEMPT_RE.fullmatch(value):
        raise ReviewInputError(f"{field} must be a bounded identifier")
    return value


def _full_oid(value: object, *, field: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not OID_RE.fullmatch(value):
        raise ReviewInputError(f"{field} must be a full lowercase Git object ID")
    return value


def _plain_int(
    value: object, *, field: str, minimum: int = 0, maximum: int = MAX_FINDINGS
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReviewInputError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ReviewInputError(f"{field} must be between {minimum} and {maximum}")
    return value


def _bounded_strings(
    value: object, *, field: str, limit: int = MAX_FINDINGS
) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise ReviewInputError(f"{field} must be a bounded string array")
    result: list[str] = []
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 500
            or "\x00" in item
        ):
            raise ReviewInputError(f"{field} must be a bounded string array")
        result.append(item)
    return result


def _audit_complete(audit: Mapping[str, Any]) -> bool:
    expected = set(FAMILY_AUDIT_DIMENSIONS[str(audit["family"])])
    dimensions = audit["dimensions"]
    observed = {
        str(item["id"]): str(item["status"])
        for item in dimensions
        if isinstance(item, Mapping)
    }
    return (
        audit["localOutcome"] == "clean"
        and not audit["localLimitations"]
        and audit["checkStatus"] == "passed"
        and audit["head"] == audit["localHead"] == audit["checkHead"]
        and set(observed) == expected
        and set(observed.values()) <= {"covered", "not-applicable"}
        and len(audit["siblingFindingIds"]) >= 2
        and audit["batchSize"] == len(audit["siblingFindingIds"])
        and len(audit["fixCommits"]) <= 1
    )


def _parse_family_finding(value: object, *, current_round: int) -> dict[str, Any]:
    keys = {
        "id",
        "provider",
        "round",
        "head",
        "family",
        "actionable",
        "disposition",
        "fixCommit",
        "siblingAuditId",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewInputError("family finding has unsupported or missing fields")
    disposition = value["disposition"]
    if disposition not in FINDING_DISPOSITIONS:
        raise ReviewInputError("family finding disposition is unsupported")
    actionable = value["actionable"]
    if not isinstance(actionable, bool):
        raise ReviewInputError("family finding actionable must be boolean")
    if not actionable and disposition in {"outstanding", "fix"}:
        raise ReviewInputError(
            "a non-actionable family finding cannot remain outstanding or selected for fix"
        )
    fix_commit = _full_oid(
        value["fixCommit"], field="family finding fixCommit", optional=True
    )
    if disposition == "fixed" and fix_commit is None:
        raise ReviewInputError("a fixed family finding requires fixCommit")
    audit_id = value["siblingAuditId"]
    if audit_id is not None:
        audit_id = _safe_id(audit_id, field="family finding siblingAuditId")
    return {
        "id": _safe_id(value["id"], field="family finding id"),
        "provider": _safe_id(value["provider"], field="family finding provider"),
        "round": _plain_int(
            value["round"], field="family finding round", minimum=1, maximum=current_round
        ),
        "head": _full_oid(value["head"], field="family finding head"),
        "family": _family_id(value["family"], field="family finding family"),
        "actionable": actionable,
        "disposition": disposition,
        "fixCommit": fix_commit,
        "siblingAuditId": audit_id,
    }


def _parse_family_audit(value: object, *, current_round: int) -> dict[str, Any]:
    keys = {
        "id",
        "family",
        "round",
        "head",
        "localReceiptId",
        "localHead",
        "localOutcome",
        "localLimitations",
        "checkHead",
        "checkStatus",
        "batchSize",
        "fixCommits",
        "siblingFindingIds",
        "dimensions",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewInputError("family audit has unsupported or missing fields")
    family = _family_id(value["family"], field="family audit family")
    outcome = value["localOutcome"]
    if outcome not in OUTCOMES - {"skipped"}:
        raise ReviewInputError("family audit localOutcome is unsupported")
    check_status = value["checkStatus"]
    if check_status not in {"passed", "failed", "unavailable"}:
        raise ReviewInputError("family audit checkStatus is unsupported")
    receipt_id = value["localReceiptId"]
    if not isinstance(receipt_id, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_id):
        raise ReviewInputError("family audit localReceiptId must be a SHA-256 digest")
    fix_commits = value["fixCommits"]
    if not isinstance(fix_commits, list) or len(fix_commits) > 1:
        raise ReviewInputError("family audit permits at most one fix commit")
    normalized_commits = [
        _full_oid(item, field="family audit fix commit") for item in fix_commits
    ]
    sibling_ids = _bounded_strings(
        value["siblingFindingIds"], field="family audit siblingFindingIds"
    )
    if len(sibling_ids) != len(set(sibling_ids)) or any(
        not ATTEMPT_RE.fullmatch(item) for item in sibling_ids
    ):
        raise ReviewInputError("family audit siblingFindingIds must be unique identifiers")
    dimensions = value["dimensions"]
    if not isinstance(dimensions, list) or len(dimensions) > 32:
        raise ReviewInputError("family audit dimensions must be a bounded array")
    expected = set(FAMILY_AUDIT_DIMENSIONS[family])
    normalized_dimensions: list[dict[str, str]] = []
    seen_dimensions: set[str] = set()
    for item in dimensions:
        if not isinstance(item, dict) or set(item) != {"id", "status"}:
            raise ReviewInputError("family audit dimension is malformed")
        identifier = item["id"]
        status_value = item["status"]
        if identifier not in expected or identifier in seen_dimensions:
            raise ReviewInputError("family audit dimension is unknown or duplicated")
        if status_value not in {"covered", "not-applicable", "missing"}:
            raise ReviewInputError("family audit dimension status is unsupported")
        seen_dimensions.add(identifier)
        normalized_dimensions.append({"id": identifier, "status": status_value})
    normalized_dimensions.sort(key=lambda item: item["id"])
    return {
        "id": _safe_id(value["id"], field="family audit id"),
        "family": family,
        "round": _plain_int(
            value["round"], field="family audit round", minimum=1, maximum=current_round
        ),
        "head": _full_oid(value["head"], field="family audit head"),
        "localReceiptId": receipt_id,
        "localHead": _full_oid(value["localHead"], field="family audit localHead"),
        "localOutcome": outcome,
        "localLimitations": _bounded_strings(
            value["localLimitations"], field="family audit localLimitations", limit=32
        ),
        "checkHead": _full_oid(value["checkHead"], field="family audit checkHead"),
        "checkStatus": check_status,
        "batchSize": _plain_int(value["batchSize"], field="family audit batchSize"),
        "fixCommits": normalized_commits,
        "siblingFindingIds": sibling_ids,
        "dimensions": normalized_dimensions,
    }


def _parse_family_extension(value: object, *, current_round: int) -> dict[str, Any]:
    keys = {"family", "afterRound", "decisionId", "approved"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewInputError("family extension has unsupported or missing fields")
    if value["decisionId"] != "review.round-extension" or value["approved"] is not True:
        raise ReviewInputError("family extension requires an approved review.round-extension decision")
    return {
        "family": _family_id(value["family"], field="family extension family"),
        "afterRound": _plain_int(
            value["afterRound"],
            field="family extension afterRound",
            minimum=1,
            maximum=current_round,
        ),
        "decisionId": "review.round-extension",
        "approved": True,
    }


def _family_gate(path: Path | None, target: Mapping[str, Any]) -> dict[str, Any]:
    if path is None:
        return {
            "schemaVersion": 1,
            "state": "inactive",
            "exactHead": target["head"],
            "currentRound": 0,
            "repeatedFamilies": [],
            "families": [],
            "roundsAvoided": 0,
            "siblingFindings": 0,
            "batchSize": 0,
        }
    raw = _read_json(path, limit=512 * 1024, label="family evidence")
    keys = {
        "schemaVersion",
        "lifecycleId",
        "currentRound",
        "currentHead",
        "blockedRedispatches",
        "findings",
        "audits",
        "extensions",
    }
    if not isinstance(raw, dict) or set(raw) != keys or raw.get("schemaVersion") != 1:
        raise ReviewInputError("family evidence must use the exact schemaVersion 1 contract")
    _safe_id(raw["lifecycleId"], field="family evidence lifecycleId")
    current_round = _plain_int(
        raw["currentRound"], field="family evidence currentRound", minimum=1
    )
    current_head = _full_oid(raw["currentHead"], field="family evidence currentHead")
    if current_head != target["head"]:
        raise ReviewInputError("family evidence does not match the exact review head")
    findings_value = raw["findings"]
    audits_value = raw["audits"]
    extensions_value = raw["extensions"]
    if not isinstance(findings_value, list) or len(findings_value) > MAX_FINDINGS:
        raise ReviewInputError("family evidence findings must be a bounded array")
    if not isinstance(audits_value, list) or len(audits_value) > MAX_FAMILY_AUDITS:
        raise ReviewInputError("family evidence audits must be a bounded array")
    if not isinstance(extensions_value, list) or len(extensions_value) > MAX_FAMILY_EXTENSIONS:
        raise ReviewInputError("family evidence extensions must be a bounded array")
    findings = [
        _parse_family_finding(item, current_round=current_round)
        for item in findings_value
    ]
    audits = [
        _parse_family_audit(item, current_round=current_round) for item in audits_value
    ]
    extensions = [
        _parse_family_extension(item, current_round=current_round)
        for item in extensions_value
    ]
    if len({item["id"] for item in findings}) != len(findings):
        raise ReviewInputError("family finding ids must be unique")
    if len({item["id"] for item in audits}) != len(audits):
        raise ReviewInputError("family audit ids must be unique")
    audit_by_id = {str(item["id"]): item for item in audits}
    for finding in findings:
        audit_id = finding["siblingAuditId"]
        if audit_id is not None and (
            audit_id not in audit_by_id
            or audit_by_id[audit_id]["family"] != finding["family"]
        ):
            raise ReviewInputError(
                "family finding siblingAuditId must reference an audit for the same family"
            )
    extension_keys = {
        (str(item["family"]), int(item["afterRound"])) for item in extensions
    }
    if len(extension_keys) != len(extensions):
        raise ReviewInputError("family extensions must be unique per family and round")
    family_rows: list[dict[str, Any]] = []
    for family in FINDING_FAMILY_IDS:
        observations = [
            item for item in findings if item["family"] == family and item["actionable"]
        ]
        rounds = sorted({int(item["round"]) for item in observations})
        if not rounds:
            continue
        repeated = len(rounds) >= 2
        complete_audits = sorted(
            (
                item
                for item in audits
                if item["family"] == family
                and _audit_complete(item)
                and (not repeated or item["round"] >= rounds[1])
            ),
            key=lambda item: (item["round"], item["id"]),
        )
        audit = complete_audits[-1] if complete_audits else None
        state = "observed"
        if repeated and audit is None:
            state = "sibling-audit-required"
        elif repeated and audit is not None and rounds[-1] > int(audit["round"]):
            extended = any(
                item["family"] == family and item["afterRound"] == rounds[-1]
                for item in extensions
            )
            state = "redispatch-eligible" if extended else "round-extension-required"
        elif repeated:
            state = "redispatch-eligible"
        dimension_status = {
            str(item["id"]): str(item["status"])
            for item in (audit["dimensions"] if audit is not None else [])
        }
        family_rows.append(
            {
                "family": family,
                "state": state,
                "observationCount": len(observations),
                "rounds": rounds,
                "auditId": audit["id"] if audit is not None else None,
                "auditComplete": audit is not None,
                "siblingFindings": len(audit["siblingFindingIds"]) if audit else 0,
                "batchSize": int(audit["batchSize"]) if audit else 0,
                "checklist": [
                    {
                        "id": identifier,
                        "status": dimension_status.get(identifier, "required"),
                    }
                    for identifier in FAMILY_AUDIT_DIMENSIONS[family]
                ],
            }
        )
    states = {row["state"] for row in family_rows}
    state = (
        "round-extension-required"
        if "round-extension-required" in states
        else "sibling-audit-required"
        if "sibling-audit-required" in states
        else "redispatch-eligible"
        if "redispatch-eligible" in states
        else "observed"
    )
    repeated_families = [
        str(row["family"])
        for row in family_rows
        if len(row["rounds"]) >= 2
    ]
    return {
        "schemaVersion": 1,
        "state": state,
        "exactHead": target["head"],
        "currentRound": current_round,
        "repeatedFamilies": repeated_families,
        "families": family_rows,
        "roundsAvoided": _plain_int(
            raw["blockedRedispatches"], field="family evidence blockedRedispatches"
        ),
        "siblingFindings": sum(int(row["siblingFindings"]) for row in family_rows),
        "batchSize": sum(int(row["batchSize"]) for row in family_rows),
    }


def build_plan(
    *,
    providers: Sequence[Provider],
    policy: Mapping[str, Any],
    target: Mapping[str, Any],
    local: str,
    local_policy: str,
    fix_policy: str,
    successor: str,
    finding_families: Sequence[str],
    family_gate: Mapping[str, Any],
    bookkeeping_evidence: Path | None,
    configuration_digest: str,
) -> dict[str, Any]:
    normalized_families = sorted(set(finding_families))
    if any(item not in FINDING_FAMILY_IDS for item in normalized_families):
        raise ReviewInputError("finding family ids must use the bounded vocabulary")
    if len(normalized_families) > 32:
        raise ReviewInputError("finding family input exceeds 32 entries")
    if successor == "repeated-family" and not normalized_families:
        raise ReviewInputError("repeated-family successor requires --finding-family")
    path_values = [str(row["path"]) for row in target["paths"] if isinstance(row, dict)]
    risk_class, reasons = classify_paths(path_values)
    allowed = set(policy["allowedDataHandling"])
    eligible = [
        provider
        for provider in providers
        if provider.enabled
        and str(target["scope"]) in provider.scopes
        and provider.data_handling in allowed
    ]
    by_id = {provider.identifier: provider for provider in eligible}
    required = tuple(str(item) for item in policy["requiredProviders"])
    missing_required = [
        identifier for identifier in required if identifier not in by_id
    ]
    if missing_required:
        raise ReviewInputError(
            f"required local provider is ineligible: {missing_required[0]}"
        )
    selected: list[Provider]
    policy_id: str
    if local == "none":
        if required or local_policy == "required":
            raise ReviewInputError(
                "local=none conflicts with required local review policy"
            )
        selected, policy_id = [], "explicit-none"
    elif local == "all":
        selected, policy_id = eligible, "explicit-all"
    elif local != "auto":
        if local not in by_id:
            raise ReviewInputError(
                f"requested local provider is unavailable or ineligible: {local}"
            )
        selected, policy_id = [by_id[local]], "explicit-provider"
    elif successor == "bookkeeping":
        _validate_bookkeeping_evidence(bookkeeping_evidence, target)
        selected, policy_id = [], "bookkeeping-successor"
    elif successor == "low-risk":
        selected = sorted(
            eligible,
            key=lambda item: (COST_TIERS.index(item.cost_tier), item.identifier),
        )[:1]
        policy_id = "low-risk-successor"
    elif (
        successor in {"high-risk", "repeated-family"}
        or risk_class == "substantive"
        or "ambiguous" in reasons
    ):
        selected = [
            provider
            for provider in eligible
            if provider.identifier in {"codex", "prism", "gito"}
        ]
        policy_id = (
            "repeated-family"
            if successor == "repeated-family"
            else "substantive-ensemble"
        )
    elif policy[risk_class] == "skip":
        selected, policy_id = [], f"{risk_class}-skip"
    else:
        selected = sorted(
            eligible,
            key=lambda item: (COST_TIERS.index(item.cost_tier), item.identifier),
        )[:1]
        policy_id = f"{risk_class}-cheapest"
    selected_ids = {provider.identifier for provider in selected}
    selected.extend(by_id[item] for item in required if item not in selected_ids)
    selected = sorted(
        {item.identifier: item for item in selected}.values(),
        key=lambda item: item.identifier,
    )
    if not selected and policy_id not in {
        "explicit-none",
        "bookkeeping-successor",
        "documentation-skip",
        "metadata-skip",
    }:
        raise ReviewInputError(
            "no eligible local review provider satisfies the selected policy"
        )
    plan = {
        "schemaVersion": 1,
        "scope": target["scope"],
        "riskClass": risk_class,
        "riskReasons": reasons,
        "providers": [_provider_row(item) for item in selected],
        "execution": "parallel"
        if len(selected) > 1
        else "serial"
        if selected
        else "skipped",
        "policyId": policy_id,
        "successor": successor,
        "findingFamilies": normalized_families,
        "familyGate": dict(family_gate),
        "localPolicy": local_policy,
        "fixPolicy": fix_policy,
        "configurationDigest": configuration_digest,
    }
    # Carried on the plan only when configured, never as an explicit null. The
    # plan is digested into policyDigest and policyDigest into the receipt
    # identity, so emitting the key unconditionally would change every existing
    # repository's digests to record that it had not opted in -- invalidating
    # cached receipts fleet-wide for a feature nobody turned on.
    ceiling = policy.get("localAdvisorySeverityCeiling")
    if ceiling is not None:
        plan["localAdvisorySeverityCeiling"] = ceiling
        # Rides the same condition, for the same reason, and earns its place by
        # moving the digest: recording the classification on each finding is a
        # receipt-shape change, so a repository already running with a ceiling
        # must not answer from a receipt cached before it. Bump this when the
        # recorded shape changes again.
        plan["localAdvisoryRecordVersion"] = 1
    plan["policyDigest"] = _digest(plan)
    return plan


def _artifact_root(repo: Path, value: str | None) -> Path:
    raw = Path(value) if value else DEFAULT_ARTIFACT_ROOT
    path = raw if raw.is_absolute() else repo / raw
    try:
        lexical = path.relative_to(repo)
        if ".." in lexical.parts:
            raise ValueError("artifact root contains parent traversal")
        resolved = path.resolve(strict=False)
        resolved.relative_to(repo)
    except (OSError, ValueError) as error:
        raise ReviewInputError(
            "review artifact root must stay inside the repository"
        ) from error
    if resolved == repo or ".git" in resolved.relative_to(repo).parts:
        raise ReviewInputError("review artifact root cannot be the repository or .git")
    current = repo
    for part in lexical.parts:
        current /= part
        if current.is_symlink():
            raise ReviewInputError(
                f"review artifact root cannot traverse a symlink: {current}"
            )
    result = run_git_minimal(
        ["check-ignore", "-q", "--", str(resolved.relative_to(repo))],
        cwd=repo,
        timeout=None,
        binary=True,
        # Preserve the pre-migration bare-subprocess semantics: the original
        # call inherited stderr so git's diagnostics surfaced in the terminal.
        stderr=None,
    )
    if result.returncode != 0:
        raise ReviewInputError("review artifact root must be ignored by Git")
    resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        resolved.chmod(0o700)
    return resolved


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        try:
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
        except BaseException:
            os.close(descriptor)
            raise
        with handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


PRISM_RULES_PATH = ".prism/rules.json"
PRISM_RULES_LIMIT = 256 * 1024

# Keys the pack refuses to hand prism, each with the reason published in the
# receipt. The shipped rules schema must not admit any of these: a key that
# validates and is then refused gives an author a file that passes every check
# available to them and fails only at review time. The two sides are bound by
# test rather than by convention -- see
# test_the_shipped_schema_admits_no_key_the_runner_refuses.
#
# A reason per key rather than one shared string, because the explanation is
# what makes the refusal actionable and no two keys will be refused for the same
# reason. These are published artifacts: keep them fixed and bounded, and never
# interpolate anything host-specific.
REFUSED_RULES_KEYS = {
    "severityOverrides": (
        "prism rules carry severityOverrides, which replaces per-finding "
        "severity with a category lookup; remove the key to have focus and "
        "required checks applied"
    ),
}


@dataclass(frozen=True)
class RulesDecision:
    """Whether prism gets a --rules flag, and the receipt record explaining it."""

    argv_extension: tuple[str, ...]
    record: dict[str, Any]


def _prism_rules(repo: Path) -> RulesDecision:
    """Resolve the repository's prism rules file into argv plus a receipt record.

    Every outcome is recorded and none is fatal. A review that runs without
    rules is exactly the behaviour that shipped before this flag existed, so
    degrading to it is always available and always better than not reviewing.
    """

    path = repo / PRISM_RULES_PATH
    if not path.is_file():
        # `is_file()` follows symlinks, so it is False for a dangling link and
        # for a directory just as it is for a genuinely missing path. Only the
        # last is `absent`; calling the others absent tells a receipt reader the
        # repository ships no rules when in fact it ships broken ones.
        if path.is_symlink() or path.exists():
            return RulesDecision(
                (),
                {
                    "status": "unreadable",
                    "path": PRISM_RULES_PATH,
                    "reason": "prism rules are not a readable regular file",
                },
            )
        return RulesDecision((), {"status": "absent", "path": PRISM_RULES_PATH})
    try:
        value = _read_json(path, limit=PRISM_RULES_LIMIT, label="prism rules")
    except ReviewInputError:
        # Deliberately not the underlying message: _read_json interpolates the
        # absolute path, and this record is published in a review receipt. The
        # path is already reported, relative, in the `path` field.
        return RulesDecision(
            (),
            {
                "status": "unreadable",
                "path": PRISM_RULES_PATH,
                "reason": "prism rules are missing, oversized, or not valid JSON",
            },
        )
    if not isinstance(value, dict):
        return RulesDecision(
            (),
            {
                "status": "unreadable",
                "path": PRISM_RULES_PATH,
                "reason": "prism rules root must be an object",
            },
        )
    refused = next((key for key in REFUSED_RULES_KEYS if key in value), None)
    if refused is not None:
        # Refusing is louder than sanitizing. Dropping the key and passing the
        # rest would hand prism a rules file the author never wrote, and the
        # receipt would report `applied` over rules that were silently edited.
        return RulesDecision(
            (),
            {
                "status": "refused",
                "path": PRISM_RULES_PATH,
                "reason": REFUSED_RULES_KEYS[refused],
            },
        )
    # Relative on purpose: _run_provider sets cwd=repo, and a relative path keeps
    # the argv stable across machines, which matters because it is persisted into
    # invocation.json and compared when a receipt is reused.
    return RulesDecision(
        ("--rules", PRISM_RULES_PATH), {"status": "applied", "path": PRISM_RULES_PATH}
    )


def _require_tree_at_head(
    repo: Path, target: Mapping[str, Any], selected: Sequence[Provider]
) -> None:
    """Refuse a delta review whose head the working tree does not hold.

    Only for providers that declared they read content from the tree. The
    alternative to refusing is what this replaces: the provider reviews the
    requested base against whatever is checked out, exits zero, and the receipt
    records a head the output does not support.

    Not applicable to ``worktree`` (the tree *is* the subject) or ``codebase``
    (already gated on a clean tree bound to one head upstream). Runs after
    ``resolve_target``, so a dirty worktree has already been reported as
    dirtiness rather than surfacing here as a confusing head mismatch.
    """
    if str(target["scope"]) != "branch_delta":
        return
    bound = [provider for provider in selected if provider.requires_tree_at_head]
    if not bound:
        return
    actual = str(_git(repo, "rev-parse", "--verify", "HEAD")).strip()
    planned = str(target["head"])
    if actual == planned:
        return
    names = ", ".join(sorted(provider.identifier for provider in bound))
    raise ReviewInputError(
        f"provider(s) {names} read file content from the working tree, which "
        f"does not hold the requested head: planned {planned}, checked out "
        f"{actual}. Review from a tree or worktree at the requested head."
    )


def _reconfirm_tree_binding(
    repo: Path, target: Mapping[str, Any], selected: Sequence[Provider]
) -> None:
    """Re-check, after the providers have run, that the tree still holds what
    the receipt is about to claim they reviewed.

    ``_require_tree_at_head`` and ``resolve_target`` bind the tree before the
    run, but a provider that reads the live checkout may run for minutes. A
    tree that moves in between leaves a receipt vouching for content no
    provider saw, which is the failure both pre-run guards exist to prevent.
    """
    scope = str(target["scope"])
    if scope == "worktree":
        # The tree is the subject, so any change to it invalidates the digest
        # every provider was pointed at.
        fresh = resolve_target(
            repo, "changes", str(target["base"]), str(target["head"])
        )
        if fresh["contentDigest"] != target["contentDigest"]:
            raise ReviewInputError(
                "working tree changed while the local review ran; rerun the "
                "stage against the current tree"
            )
        return
    if not any(provider.requires_tree_at_head for provider in selected):
        return
    # Same two conditions resolve_target and _require_tree_at_head enforced
    # before the run: the requested head is checked out, and nothing else is.
    _require_tree_at_head(repo, target, selected)
    if str(_git(repo, "status", "--porcelain=v1", "--untracked-files=all")):
        names = ", ".join(
            sorted(
                provider.identifier
                for provider in selected
                if provider.requires_tree_at_head
            )
        )
        raise ReviewInputError(
            f"the working tree became dirty while provider(s) {names} read "
            "file content from it; rerun the stage against a clean tree at "
            "the requested head"
        )


def _expand_argv(
    provider: Provider,
    target: Mapping[str, Any],
    attempt_dir: Path,
    context_path: Path,
    repo: Path,
    rules: RulesDecision,
) -> list[str]:
    paths = [str(row["path"]) for row in target["paths"] if isinstance(row, dict)]
    path_csv = ",".join(paths)
    scope = str(target["scope"])
    if provider.adapter == "prism":
        if scope == "branch_delta":
            result = [
                "prism",
                "review",
                "range",
                f"{target['base']}..{target['head']}",
                "--format",
                "json",
            ]
        elif scope == "codebase":
            result = ["prism", "review", "codebase", "--format", "json"]
        else:
            if any("," in path for path in paths):
                raise ReviewInputError(
                    "Prism worktree review cannot safely encode a path containing a comma"
                )
            result = [
                "prism",
                "review",
                "codebase",
                "--paths",
                path_csv,
                "--format",
                "json",
            ]
        result += list(rules.argv_extension)
    elif provider.adapter == "gito":
        output = str(attempt_dir / "provider-output")
        if scope == "codebase":
            result = [
                "gito",
                "review",
                "--all",
                "--path",
                str(repo),
                "--out",
                output,
            ]
        elif scope == "branch_delta":
            # --what is the head half of the range. Without it gito supplies its
            # own head from the working tree, so the reviewed range is
            # base..<checked out> rather than base..head.
            result = [
                "gito",
                "review",
                "--what",
                str(target["head"]),
                "--vs",
                str(target["base"]),
                "--out",
                output,
            ]
        else:
            # worktree: the subject is the uncommitted state, which is exactly
            # the head gito supplies for itself. Naming one would be wrong.
            result = [
                "gito",
                "review",
                "--vs",
                str(target["base"]),
                "--out",
                output,
            ]
    elif provider.adapter == "codex":
        if scope == "codebase":
            raise ReviewInputError(
                "codex adapter reviews a diff and does not support codebase scope"
            )
        # The schema and answer files live in the attempt directory, which
        # _run_provider creates and seeds before the process starts.
        result = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "-C",
            str(repo),
            # The reviewed checkout must not instruct its own reviewer: a
            # changed AGENTS.md would otherwise load above this prompt.
            "-c",
            "project_doc_max_bytes=0",
            "--output-schema",
            str(attempt_dir / CODEX_SCHEMA_FILE),
            "--output-last-message",
            str(attempt_dir / CODEX_ANSWER_FILE),
            _codex_prompt(scope, str(target["base"]), str(target["head"])),
        ]
    else:
        if any("," in path for path in paths) and any(
            "{paths}" in item for item in provider.argv
        ):
            raise ReviewInputError(
                f"provider {provider.identifier} cannot safely encode a path containing a comma"
            )
        substitutions = {
            "{repo}": str(repo),
            "{base}": str(target["base"]),
            "{head}": str(target["head"]),
            "{paths}": path_csv,
            "{artifact}": str(attempt_dir),
            "{context}": str(context_path),
        }
        result = []
        for item in provider.argv:
            for marker, replacement in substitutions.items():
                item = item.replace(marker, replacement)
            result.append(item)
    if (
        any(len(item) > MAX_EXPANDED_ARGV_BYTES for item in result)
        or sum(len(os.fsencode(item)) + 1 for item in result) > MAX_EXPANDED_ARGV_BYTES
    ):
        raise ReviewInputError(
            f"provider {provider.identifier} expanded argv exceeds {MAX_EXPANDED_ARGV_BYTES} bytes"
        )
    return result


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        process.wait(timeout=5)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _cancel_active_processes() -> None:
    with ACTIVE_PROCESSES_LOCK:
        processes = tuple(ACTIVE_PROCESSES)
    for process in processes:
        _terminate(process)


def _handle_termination(signum: int, _frame: object) -> None:
    del signum
    CANCELLATION_EVENT.set()
    _cancel_active_processes()


def _parse_json_payload(payload: bytes) -> object | None:
    if len(payload) > MAX_OUTPUT_BYTES:
        return None
    try:
        return json.loads(payload.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        return None


def _parse_argv_payload(stdout: bytes) -> dict[str, Any] | None:
    value = _parse_json_payload(stdout)
    if not isinstance(value, dict) or value.get("status") not in OUTCOMES:
        return None
    findings = value.get("findings", [])
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        return None
    return value


def _prism_payload(stdout: bytes) -> dict[str, Any] | None:
    value = _parse_json_payload(stdout)
    if not isinstance(value, dict) or not isinstance(value.get("findings"), list):
        return None
    raw_findings = value["findings"]
    if len(raw_findings) > MAX_FINDINGS:
        return None
    findings: list[dict[str, Any]] = []
    for raw in raw_findings:
        if not isinstance(raw, dict):
            return None
        locations = raw.get("locations")
        location = locations[0] if isinstance(locations, list) and locations else {}
        if not isinstance(location, dict):
            location = {}
        lines = location.get("lines")
        line = lines.get("start") if isinstance(lines, dict) else None
        findings.append(
            {
                "path": location.get("path"),
                "line": line,
                "severity": raw.get("severity"),
                "summary": raw.get("title") or raw.get("message"),
                "family": raw.get("category"),
            }
        )
    return {"status": "findings" if findings else "clean", "findings": findings}


def _gito_payload(attempt_dir: Path) -> dict[str, Any] | None:
    path = attempt_dir / "provider-output" / "code-review-report.json"
    try:
        value = _read_json(path, limit=MAX_OUTPUT_BYTES, label="Gito report")
    except ReviewInputError:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("issues"), dict):
        return None
    raw_total = value.get("total_issues")
    if (
        not isinstance(raw_total, int)
        or isinstance(raw_total, bool)
        or not 0 <= raw_total <= MAX_FINDINGS
    ):
        return None
    findings: list[dict[str, Any]] = []
    for group_path, raw_group in value["issues"].items():
        if not isinstance(group_path, str) or not isinstance(raw_group, list):
            return None
        for raw in raw_group:
            if not isinstance(raw, dict) or len(findings) >= MAX_FINDINGS:
                return None
            affected = raw.get("affected_lines")
            location = affected[0] if isinstance(affected, list) and affected else {}
            if not isinstance(location, dict):
                location = {}
            severity = raw.get("severity")
            if isinstance(severity, int) and not isinstance(severity, bool):
                severity_name = {1: "low", 2: "medium", 3: "high"}.get(severity)
                if severity_name is None:
                    return None
            elif severity is None:
                severity_name = "unspecified"
            elif isinstance(severity, str):
                severity_name = severity.casefold()
                if severity_name not in FINDING_SEVERITY_RANK:
                    return None
            else:
                return None
            tags = raw.get("tags")
            family = tags[0] if isinstance(tags, list) and tags else "other"
            findings.append(
                {
                    "path": raw.get("file") or group_path,
                    "line": location.get("start_line"),
                    "severity": severity_name,
                    "summary": raw.get("title") or raw.get("details"),
                    "family": family,
                }
            )
    if raw_total != len(findings):
        return None
    return {"status": "findings" if findings else "clean", "findings": findings}


def _codex_payload(attempt_dir: Path) -> dict[str, Any] | None:
    """Read the schema-constrained answer codex wrote for this attempt.

    codex exec enforces CODEX_OUTPUT_SCHEMA on the final message, so the
    answer is already in the normalized finding shape; this only bounds it.
    """
    path = attempt_dir / CODEX_ANSWER_FILE
    try:
        value = _read_json(path, limit=MAX_OUTPUT_BYTES, label="codex answer")
    except ReviewInputError:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("findings"), list):
        return None
    raw_findings = value["findings"]
    if len(raw_findings) > MAX_FINDINGS:
        return None
    findings: list[dict[str, Any]] = []
    for raw in raw_findings:
        if not isinstance(raw, dict):
            return None
        severity = raw.get("severity")
        if severity not in FINDING_SEVERITY_RANK:
            return None
        line = raw.get("line")
        findings.append(
            {
                "path": raw.get("path"),
                "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
                "severity": severity,
                "summary": raw.get("summary"),
                "family": raw.get("family"),
            }
        )
    return {"status": "findings" if findings else "clean", "findings": findings}


def _parse_provider_payload(
    provider: Provider, stdout: bytes, attempt_dir: Path
) -> dict[str, Any] | None:
    if provider.adapter == "prism":
        return _prism_payload(stdout)
    if provider.adapter == "gito":
        return _gito_payload(attempt_dir)
    if provider.adapter == "codex":
        return _codex_payload(attempt_dir)
    return _parse_argv_payload(stdout)


def _bounded_provider_findings(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings: list[dict[str, Any]] = []
    for raw in value[:MAX_FINDINGS]:
        if not isinstance(raw, dict):
            continue
        raw_path = str(raw.get("path") or "")
        try:
            path = _safe_relative(raw_path) if raw_path else ""
        except ReviewInputError:
            path = ""
        raw_line = raw.get("line")
        findings.append(
            {
                "path": _bounded(path, 500),
                "line": raw_line
                if isinstance(raw_line, int)
                and not isinstance(raw_line, bool)
                and raw_line > 0
                else None,
                "severity": _bounded(str(raw.get("severity") or "unspecified"), 40),
                "summary": _bounded(str(raw.get("summary") or "provider finding"), 500),
                "family": _bounded(str(raw.get("family") or "other"), 80),
                "disposition": "outstanding",
            }
        )
    return findings


def _run_provider(
    provider: Provider,
    *,
    argv: Sequence[str],
    repo: Path,
    run_dir: Path,
    environment: Mapping[str, str],
    rules: Mapping[str, Any] | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    attempt_dir = run_dir / provider.identifier
    attempt_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    if provider.adapter == "codex":
        (attempt_dir / CODEX_SCHEMA_FILE).write_text(
            json.dumps(CODEX_OUTPUT_SCHEMA), encoding="utf-8"
        )
    started = time.time()
    base = {
        "provider": _provider_row(provider),
        "startedAt": started,
        # Recorded for every provider, not just prism: a reader comparing two
        # attempts should not have to know which adapters consult a rules file.
        "rules": dict(rules) if rules is not None else {"status": "absent"},
        "artifact": str(attempt_dir.relative_to(run_dir.parent.parent)),
    }
    _atomic_json(attempt_dir / "attempt.json", {**base, "status": "running"})
    if CANCELLATION_EVENT.is_set():
        result = {
            **base,
            "status": "cancelled",
            "exitCode": None,
            "durationMs": 0,
            "diagnostic": "provider cancelled before start",
            "findings": [],
        }
        _atomic_json(attempt_dir / "attempt.json", result)
        return result
    executable = shutil.which(argv[0], path=environment.get("PATH"))
    if executable is None or unavailable_reason is not None:
        result = {
            **base,
            "status": "unavailable",
            "exitCode": None,
            "durationMs": 0,
            "diagnostic": unavailable_reason or f"{argv[0]} is not available",
            "findings": [],
        }
        _atomic_json(attempt_dir / "attempt.json", result)
        return result
    stdout = b""
    stderr = b""
    exit_code: int | None = None
    status_value = "failed"
    process: subprocess.Popen[bytes] | None = None
    try:
        with (
            tempfile.TemporaryFile(mode="w+b", dir=attempt_dir) as stdout_stream,
            tempfile.TemporaryFile(mode="w+b", dir=attempt_dir) as stderr_stream,
        ):
            try:
                process = subprocess.Popen(
                    list(argv),
                    cwd=repo,
                    env=dict(environment),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    start_new_session=os.name == "posix",
                )
                with ACTIVE_PROCESSES_LOCK:
                    ACTIVE_PROCESSES.add(process)
                if CANCELLATION_EVENT.is_set():
                    _terminate(process)
                try:
                    process.communicate(timeout=provider.timeout_seconds)
                    exit_code = process.returncode
                    status_value = provider.outcome_by_exit.get(exit_code, "failed")
                except subprocess.TimeoutExpired:
                    _terminate(process)
                    try:
                        process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        stderr += b"\nprovider process did not terminate after timeout"
                    exit_code = 124
                    status_value = "failed"
                    stderr += (
                        f"\nprovider timed out after {provider.timeout_seconds}s".encode()
                    )
                if CANCELLATION_EVENT.is_set():
                    status_value = "cancelled"
            except OSError as error:
                if process is not None and process.poll() is None:
                    _terminate(process)
                stderr += str(error).encode()
                status_value = (
                    "cancelled" if CANCELLATION_EVENT.is_set() else "failed"
                )
            finally:
                if process is not None:
                    with ACTIVE_PROCESSES_LOCK:
                        ACTIVE_PROCESSES.discard(process)
            stdout_stream.seek(0)
            stdout = stdout_stream.read(MAX_OUTPUT_BYTES)
            stderr_stream.seek(0)
            stderr = (stderr_stream.read(MAX_OUTPUT_BYTES) + stderr)[
                :MAX_OUTPUT_BYTES
            ]
    except OSError as error:
        stderr = (stderr + str(error).encode())[:MAX_OUTPUT_BYTES]
        status_value = (
            "cancelled" if CANCELLATION_EVENT.is_set() else "failed"
        )
    payload = _parse_provider_payload(provider, stdout, attempt_dir)
    findings = (
        _bounded_provider_findings(payload.get("findings", [])) if payload else []
    )
    if payload is not None:
        payload_status = str(payload["status"])
        if status_value not in TERMINAL_FAILURES:
            status_value = (
                "findings"
                if findings
                or status_value == "findings"
                or payload_status == "findings"
                else payload_status
            )
    elif exit_code == 0:
        status_value = "failed"
        stderr += b"\nprovider did not produce a valid structured review report"
    (attempt_dir / "stdout.txt").write_bytes(stdout)
    (attempt_dir / "stderr.txt").write_bytes(stderr[:MAX_OUTPUT_BYTES])
    result = {
        **base,
        "status": status_value,
        "exitCode": exit_code,
        "durationMs": max(0, int((time.time() - started) * 1000)),
        "diagnostic": _bounded(
            stderr.decode("utf-8", "replace")
            or stdout.decode("utf-8", "replace")
            or status_value
        ),
        "findings": findings,
    }
    _atomic_json(attempt_dir / "attempt.json", result)
    return result


def _normalize_findings(
    attempts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        provider = attempt.get("provider")
        provider_id = provider.get("id") if isinstance(provider, dict) else "unknown"
        findings = attempt.get("findings", [])
        if not isinstance(findings, list):
            continue
        for raw in findings:
            if not isinstance(raw, dict):
                continue
            summary = _bounded(str(raw.get("summary") or "provider finding"), 500)
            path = _bounded(str(raw.get("path") or ""), 500)
            line = raw.get("line") if isinstance(raw.get("line"), int) else None
            severity = _bounded(str(raw.get("severity") or "unspecified"), 40)
            source_family = _bounded(str(raw.get("family") or "other"), 80) or "other"
            family = (
                source_family if source_family in FINDING_FAMILY_IDS else "other"
            )
            key = _digest({"path": path, "line": line, "summary": summary.casefold()})
            row = groups.setdefault(
                key,
                {
                    "id": key[:16],
                    "path": path or None,
                    "line": line,
                    "severity": severity,
                    "summary": summary,
                    "family": family,
                    "families": [family],
                    "sourceFamilies": [source_family],
                    "disposition": "outstanding",
                    "providers": [],
                },
            )
            if FINDING_SEVERITY_RANK.get(severity, 0) > FINDING_SEVERITY_RANK.get(
                str(row["severity"]), 0
            ):
                row["severity"] = severity
            families = row["families"]
            if isinstance(families, list) and family not in families:
                families.append(family)
                families.sort()
                row["family"] = families[0]
            source_families = row["sourceFamilies"]
            if (
                isinstance(source_families, list)
                and source_family not in source_families
            ):
                source_families.append(source_family)
                source_families.sort()
            providers = row["providers"]
            if isinstance(providers, list) and provider_id not in providers:
                providers.append(provider_id)
                providers.sort()
    return sorted(
        groups.values(),
        key=lambda row: (str(row["path"]), int(row["line"] or 0), str(row["id"])),
    )


def _aggregate_outcome(attempts: Sequence[Mapping[str, Any]]) -> str:
    if not attempts:
        return "skipped"
    statuses = {str(item.get("status")) for item in attempts}
    for status_value in ("findings", "failed", "unavailable", "cancelled"):
        if status_value in statuses:
            return status_value
    if statuses <= {"clean", "skipped"}:
        return "clean" if "clean" in statuses else "skipped"
    return "failed"


def _parse_local_dispositions(values: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Parse ``<stable-id>=rebutted`` and ``<stable-id>=miscited@<path>:<line>``.

    ``miscited`` carries an evidence obligation ``rebutted`` does not: the
    caller states where they looked. The pack records that citation beside the
    finding's own and never verifies it by reading the checkout -- doing so
    would make the gate depend on worktree state the receipt cannot pin, and a
    receipt has to be replayable from its own contents.
    """

    dispositions: dict[str, dict[str, Any]] = {}
    for value in values:
        # rpartition splits on the LAST "=" so that an id containing "=" keeps
        # parsing exactly as it does today. The citation therefore rides inside
        # the value, and the id grammar below is unchanged.
        identifier, separator, remainder = value.rpartition("=")
        disposition, marker, citation = remainder.partition("@")
        if (
            not separator
            or not identifier
            or len(identifier) > 240
            or any(ord(character) < 32 for character in identifier)
            or disposition not in LOCAL_DISPOSITION_VALUES
        ):
            _reject_local_disposition(value)
        if disposition == "miscited":
            if not marker:
                raise ReviewInputError(
                    "miscited requires a citation as <path>:<line>"
                )
            record = _parse_miscited_citation(citation)
        elif disposition == "accepted":
            if not marker:
                raise ReviewInputError("accepted requires a reason as @<reason>")
            record = _parse_accepted_reason(citation)
        elif marker:
            raise ReviewInputError(
                "only miscited and accepted accept an @ payload"
            )
        else:
            record = {"disposition": disposition}
        if identifier in dispositions:
            raise ReviewInputError("local disposition ids must be unique")
        dispositions[identifier] = record
    return dispositions


def _reject_local_disposition(value: str) -> NoReturn:
    """Raise for an unparseable ``--local-disposition``, diagnosing the `=` trap.

    A citation path containing "=" is cut in the wrong place by the rpartition
    above, so it arrives at the vocabulary check as nonsense and would otherwise
    be reported as an unsupported disposition. The value is only inspected here,
    on the failure path, so a legitimate id containing "=" never reaches it.
    """

    _, _, tail = value.partition("=")
    verb, marker, rest = tail.partition("@")
    if marker and verb == "miscited" and "=" in rest:
        raise ReviewInputError("a miscited citation path cannot contain '='")
    if marker and verb == "accepted" and "=" in rest:
        raise ReviewInputError("an accepted reason cannot contain '='")
    raise ReviewInputError(
        "local dispositions must use <stable-id>=rebutted, "
        "<stable-id>=miscited@<path>:<line>, or <stable-id>=accepted@<reason>"
    )


def _parse_accepted_reason(reason: str) -> dict[str, Any]:
    """Bound the one ground whose claim cannot be checked at all.

    ``rebutted`` asserts the finding is untrue in the checkout and ``miscited``
    asserts the cited location does not hold it. Both can be wrong, and a
    reader can go and look. An acceptance concedes the finding is true, so
    there is nothing left to check and the reason is the whole of what makes
    the waiver attributable -- which is why it is required rather than
    optional. Free text is trivially satisfiable and this does not pretend
    otherwise: the point is that the receipt carries a signed statement where
    it would otherwise carry a fabricated rebuttal.

    A reason containing "=" never reaches here. ``rpartition`` upstream splits
    on the last one, so it is diagnosed in ``_reject_local_disposition``.
    """

    if not reason:
        raise ReviewInputError("accepted requires a reason as @<reason>")
    if len(reason) > MAX_ACCEPTED_REASON or any(
        ord(character) < 32 for character in reason
    ):
        raise ReviewInputError("accepted reason is unsafe or unbounded")
    return {"disposition": "accepted", "reason": reason}


def _parse_miscited_citation(citation: str) -> dict[str, Any]:
    """Split ``<path>:<line>`` into the record stored beside the finding."""

    path, colon, line = citation.rpartition(":")
    # ASCII digits only. ``str.isdigit`` is true for characters ``int`` refuses
    # -- "\u00b2" among them -- so accepting its whole class hands the bounded
    # ReviewInputError contract to an uncaught ValueError from ``int`` below.
    if (
        not colon
        or not path
        or not line
        # CPython refuses int() on more than 4300 digits with a plain
        # ValueError, so the length bound is part of the contract too.
        or len(line) > len(str(MAX_CITATION_LINE))
        or not set(line) <= ASCII_DIGITS
    ):
        raise ReviewInputError("miscited requires a citation as <path>:<line>")
    if (
        len(path) > 500
        or PurePosixPath(path).is_absolute()
        or ".." in PurePosixPath(path).parts
        or any(ord(character) < 32 for character in path)
    ):
        raise ReviewInputError("miscited citation path is unsafe or unbounded")
    number = int(line)
    if not 0 < number <= MAX_CITATION_LINE:
        raise ReviewInputError("miscited citation line is out of range")
    return {"disposition": "miscited", "path": str(PurePosixPath(path)), "line": number}


def _apply_local_dispositions(
    findings: Sequence[MutableMapping[str, Any]],
    dispositions: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Record caller dispositions against findings already present in the receipt.

    An id that matches no finding is an error rather than a no-op: it is almost
    always a stale id copied from an earlier head, and silently accepting it
    would open the gate for a finding nobody actually reviewed.

    The value written to ``disposition`` is the bare vocabulary member, never
    the raw argument: ``FINDING_DISPOSITIONS`` is validated elsewhere, so
    storing ``miscited@path:3`` there would produce a receipt that fails its own
    check. A miscitation's evidence goes in its own field, beside the location
    the provider claimed, so a reader can compare the two.
    """

    if not dispositions:
        return {}
    known = {str(item.get("id")): item for item in findings}
    unknown = sorted(set(dispositions) - set(known))
    if unknown:
        raise ReviewInputError(
            "local disposition ids match no finding at this head: "
            + ", ".join(unknown[:8])
        )
    applied: dict[str, str] = {}
    for identifier, record in dispositions.items():
        disposition = str(record["disposition"])
        finding = known[identifier]
        finding["disposition"] = disposition
        if disposition == "miscited":
            finding["dispositionCitation"] = {
                "path": record["path"],
                "line": record["line"],
            }
        elif disposition == "accepted":
            # Its own key, not a reuse of dispositionCitation. Sharing the
            # field would make an acceptance structurally indistinguishable
            # from a miscitation, which is the distinction this ground exists
            # to draw.
            finding["dispositionReason"] = record["reason"]
        applied[identifier] = disposition
    return applied


def _redispose_receipt(
    receipt: MutableMapping[str, Any],
    dispositions: Mapping[str, Mapping[str, Any]],
    local_policy: str,
) -> None:
    """Apply rebuttals to a stored receipt and recompute what they affect.

    Provider evidence is left exactly as recorded; only the caller-owned
    disposition fields and the gate derived from them change.
    """

    findings = receipt.get("findings")
    if not isinstance(findings, list):
        raise ReviewInputError("stored local review receipt has no findings list")
    applied = _apply_local_dispositions(findings, dispositions)
    plan = receipt.get("plan")
    ceiling = (
        plan.get("localAdvisorySeverityCeiling")
        if isinstance(plan, Mapping)
        else None
    )
    outstanding, advisory, dispositioned, accepted = _classify_findings(
        findings, ceiling
    )
    disposition = receipt.get("disposition")
    if not isinstance(disposition, dict):
        raise ReviewInputError("stored local review receipt has no disposition block")
    disposition["outstanding"] = outstanding
    disposition["advisory"] = advisory
    disposition["dispositioned"] = dispositioned
    disposition["accepted"] = accepted
    recorded = dict(disposition.get("localDispositions") or {})
    recorded.update(applied)
    disposition["localDispositions"] = recorded
    family_gate = plan.get("familyGate", {}) if isinstance(plan, Mapping) else {}
    # Re-gating a stored receipt: ``attempts`` is not in scope here, so the
    # degraded fact comes from the record the original run wrote rather than
    # being recomputed. That is also the right semantics -- a disposition must
    # not silently clear a limitation it did not address. A malformed or absent
    # list reads as empty, which is not a hole: a run in which every provider
    # died still reports an outcome in TERMINAL_FAILURES and is caught by the
    # other half of the branch.
    confidence = receipt.get("confidence")
    stored_limitations = (
        confidence.get("limitations") if isinstance(confidence, Mapping) else None
    )
    receipt["remoteGate"] = _remote_gate(
        str(receipt.get("outcome")),
        outstanding,
        local_policy,
        family_gate,
        findings_present=bool(findings),
        advisory=advisory,
        dispositioned=dispositioned,
        accepted=accepted,
        degraded=bool(stored_limitations)
        if isinstance(stored_limitations, list)
        else False,
    )


def _is_advisory(finding: Mapping[str, Any], ceiling: str | None) -> bool:
    """Is this finding advisory under the repository's configured ceiling?

    The provider supplies a key; policy supplies the meaning. ``severity`` is
    only ever a lookup key into a classification the reviewed repository owns,
    never a decision in itself -- otherwise a provider could open the gate by
    labelling its own finding ``low``.
    """

    if ceiling is None:
        return False
    severity = str(finding.get("severity") or "unspecified")
    rank = FINDING_SEVERITY_RANK.get(severity, 0)
    # Rank 0 is "unspecified" and anything outside the vocabulary. A provider
    # that omits or garbles its classification gets the strict gate, so
    # omission is never an escape.
    if rank == 0:
        return False
    # The floor no policy can lower. Redundant while ADVISORY_CEILING_VALUES
    # stops at "medium", and deliberately kept so that widening that tuple
    # later cannot silently make "high" releasable.
    if rank >= FINDING_SEVERITY_RANK["high"]:
        return False
    return rank <= FINDING_SEVERITY_RANK[ceiling]


def _classify_findings(
    findings: Sequence[MutableMapping[str, Any]],
    ceiling: str | None,
) -> tuple[int, int, int, int]:
    """Record each finding's classification and split into
    (blocking, advisory, dispositioned, accepted).

    The recording and the counting are one traversal of one predicate on
    purpose. Counting here and marking somewhere else would give the receipt
    two answers to the same question, which is the defect this function was
    changed to remove -- and the summary would be the one nobody could check.

    ``advisory`` is popped from every finding before anything is written, and
    written back only where the classification actually applies: outstanding,
    under a configured ceiling. So the key is present exactly where the current
    plan's ceiling classified it, this pass, with no second condition to get
    wrong when a finding leaves ``outstanding``. Popping an absent key is a
    no-op, so a strict repository's receipt is untouched.

    ``blocking`` keeps the exact meaning the old single ``outstanding`` count
    had whenever no ceiling is configured, which is what makes "absent means
    today's behaviour" checkable by running the existing suite unchanged.

    ``accepted`` is counted apart from ``dispositioned`` rather than folded in
    with it. A rebuttal says the finding was not real; an acceptance says it is
    real and stands. Summing them would leave a reader unable to tell a receipt
    that refuted its findings from one that waived them.
    """

    blocking = advisory = dispositioned = accepted = 0
    for item in findings:
        if not isinstance(item, MutableMapping):
            continue
        item.pop("advisory", None)
        disposition = item.get("disposition")
        # Tested ahead of the membership branch below, which now contains
        # "accepted" as well: reverse these two and every waiver is silently
        # folded into ``dispositioned``, with all four counts still summing
        # correctly and nothing else looking wrong.
        if disposition == "accepted":
            accepted += 1
        elif disposition in LOCAL_DISPOSITION_VALUES:
            dispositioned += 1
        elif disposition == "outstanding":
            released = _is_advisory(item, ceiling)
            if ceiling is not None:
                item["advisory"] = released
            if released:
                advisory += 1
            else:
                blocking += 1
    return blocking, advisory, dispositioned, accepted


def _remote_gate(
    outcome: str,
    outstanding: int,
    local_policy: str,
    family_gate: Mapping[str, Any],
    *,
    findings_present: bool = True,
    advisory: int = 0,
    dispositioned: int = 0,
    accepted: int = 0,
    degraded: bool = False,
) -> dict[str, Any]:
    # A provider that reports ``findings`` but lists none has given evidence
    # nobody can inspect, rebut, or classify by severity, so it still blocks --
    # and it blocks ahead of every release path below. Otherwise the count of
    # findings left outstanding is what decides: rebutted ones do not gate, and
    # neither do ones the repository's policy classifies as advisory.
    if outstanding or (outcome == "findings" and not findings_present):
        return {"state": "blocked", "reason": "actionable-local-findings"}
    family_state = family_gate.get("state")
    if family_state in {"sibling-audit-required", "round-extension-required"}:
        return {"state": "blocked", "reason": family_state}
    # ``outcome`` answers what the providers *found*; it is not a verdict, and
    # it cannot express "found things and also one lane died" -- findings
    # outrank failure in _aggregate_outcome, deliberately, so that a run which
    # found real problems does not report them as a failure. ``degraded``
    # carries the other half of the fact, from the same limitations list the
    # receipt already records, so the gate's verdict cannot contradict the
    # receipt's own evidence.
    if degraded or outcome in TERMINAL_FAILURES:
        return {
            "state": "blocked"
            if local_policy == "required"
            else "eligible-with-limitations",
            "reason": "required-local-review-failed"
            if local_policy == "required"
            else "local-review-limited",
        }
    # Report the strongest claim the receipt actually supports, so a reader is
    # never told "clean" about a receipt that was released rather than empty.
    #
    # An acceptance ranks ahead of every other claim, because the rung that
    # matters most is the weakest release ground -- the one carrying risk. A
    # rebuttal says the finding was not real. An advisory release says policy
    # did not care. An acceptance says it is real, it stands, and someone
    # signed for it. Ranked behind the others, a waiver in a receipt that also
    # rebutted something would be invisible to a reader who consults this
    # reason alone.
    if accepted:
        return {"state": "eligible", "reason": "local-findings-accepted"}
    if dispositioned:
        return {"state": "eligible", "reason": "local-findings-dispositioned"}
    if advisory:
        return {"state": "eligible", "reason": "local-advisory-released"}
    return {"state": "eligible", "reason": "local-stage-terminal"}


def _receipt_identity(target: Mapping[str, Any], plan: Mapping[str, Any]) -> str:
    return _digest(
        {
            "schemaVersion": 1,
            "target": target,
            "policyDigest": plan["policyDigest"],
            "providers": plan["providers"],
        }
    )


def _validate_reusable(
    value: object,
    *,
    target: Mapping[str, Any],
    plan: Mapping[str, Any],
    identity: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("schemaVersion") != 1 or value.get("receiptId") != identity:
        return None
    if value.get("target") != target or value.get("plan") != plan:
        return None
    if value.get("outcome") not in OUTCOMES:
        return None
    return value


def cheapest_fallbacks(
    providers: Sequence[Provider],
    policy: Mapping[str, Any],
    target: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> list[Provider]:
    """Providers to try, cheapest first, when a ``*-cheapest`` plan's sole
    provider reports unavailable.

    A cost-free lane such as codex is always the cheapest, so without this a
    machine missing that lane would run no review at all under the
    documentation, metadata, and low-risk policies. Computed outside the plan
    so the plan's shape, and therefore every receipt digest, is unchanged.
    """
    policy_id = str(plan["policyId"])
    # Every policy that selects exactly one provider by cost, not only the
    # `<risk>-cheapest` family: `low-risk-successor` picks the same way and
    # would otherwise strand a successor run on a single unavailable lane.
    if not policy_id.endswith("-cheapest") and policy_id != "low-risk-successor":
        return []
    selected = {str(row["id"]) for row in plan["providers"] if isinstance(row, dict)}
    allowed = set(policy["allowedDataHandling"])
    eligible = [
        provider
        for provider in providers
        if provider.enabled
        and str(target["scope"]) in provider.scopes
        and provider.data_handling in allowed
        and provider.identifier not in selected
    ]
    return sorted(
        eligible, key=lambda item: (COST_TIERS.index(item.cost_tier), item.identifier)
    )


def execute(
    *,
    repo: Path,
    artifact_root: Path,
    attempt_id: str,
    target: Mapping[str, Any],
    plan: Mapping[str, Any],
    providers: Sequence[Provider],
    local_policy: str,
    fix_policy: str,
    allow_reuse: bool,
    dispositions: Mapping[str, Mapping[str, Any]] | None = None,
    fallbacks: Sequence[Provider] = (),
) -> tuple[dict[str, Any], bool]:
    supplied = dict(dispositions or {})
    identity = _receipt_identity(target, plan)
    receipt_path = artifact_root / "receipts" / f"{identity}.json"
    if allow_reuse and receipt_path.exists():
        value = _read_json(
            receipt_path, limit=2 * 1024 * 1024, label="local review receipt"
        )
        reusable = _validate_reusable(
            value, target=target, plan=plan, identity=identity
        )
        if reusable is None:
            raise ReviewInputError(
                "stored local review receipt failed exact-match validation"
            )
        if supplied:
            # A rebuttal is the caller's judgement about evidence already in the
            # receipt, not new evidence, so it applies to a reused receipt
            # without re-running any provider.
            _redispose_receipt(reusable, supplied, local_policy)
            _atomic_json(receipt_path, reusable)
        return reusable, True
    run_dir = artifact_root / "runs" / attempt_id
    selected_ids = [
        str(row["id"]) for row in plan["providers"] if isinstance(row, dict)
    ]
    selected = [
        provider for provider in providers if provider.identifier in selected_ids
    ]
    context_path = run_dir / "review-context.json"
    _require_tree_at_head(repo, target, selected)
    # Once per run, not once per provider: the decision depends only on `repo`.
    rules_decision = _prism_rules(repo)
    commands = {
        provider.identifier: _expand_argv(
            provider,
            target,
            run_dir / provider.identifier,
            context_path,
            repo,
            rules_decision,
        )
        for provider in selected
    }
    try:
        run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise ReviewInputError(
            f"attempt {attempt_id} already exists without a reusable exact receipt; reconcile it before retrying"
        ) from None
    _atomic_json(
        run_dir / "invocation.json",
        {"schemaVersion": 1, "attemptId": attempt_id, "target": target, "plan": plan},
    )
    _atomic_json(
        context_path,
        {
            "schemaVersion": 1,
            "targetIdentity": target["identity"],
            "riskClass": plan["riskClass"],
            "riskReasons": plan["riskReasons"],
            "findingFamilies": plan["findingFamilies"],
            "confidenceCredit": {"granted": False},
        },
    )
    tainted = codex_instruction_surfaces(
        [str(row["path"]) for row in target["paths"] if isinstance(row, dict)]
    )
    codex_reason = (
        "the reviewed change edits instruction surfaces codex loads "
        f"({', '.join(tainted[:3])}{'...' if len(tainted) > 3 else ''}), so this "
        "lane cannot review it independently"
        if tainted
        else None
    )
    if selected:
        try:
            environment, _, _ = build_tool_environment(repo=repo)
        except CacheSetupError as error:
            raise ReviewInputError(str(error)) from error
        with ThreadPoolExecutor(
            max_workers=len(selected), thread_name_prefix="sd-review"
        ) as pool:
            futures = [
                pool.submit(
                    _run_provider,
                    provider,
                    argv=commands[provider.identifier],
                    repo=repo,
                    run_dir=run_dir,
                    environment=environment,
                    rules=(
                        rules_decision.record
                        if provider.adapter == "prism"
                        else {"status": "not-applicable", "adapter": provider.adapter}
                    ),
                    unavailable_reason=(
                        codex_reason if provider.adapter == "codex" else None
                    ),
                )
                for provider in selected
            ]
            attempts = [future.result() for future in futures]
        for fallback in fallbacks:
            if any(item["status"] != "unavailable" for item in attempts):
                break
            _require_tree_at_head(repo, target, [fallback])
            attempts.append(
                _run_provider(
                    fallback,
                    argv=_expand_argv(
                        fallback,
                        target,
                        run_dir / fallback.identifier,
                        context_path,
                        repo,
                        rules_decision,
                    ),
                    repo=repo,
                    run_dir=run_dir,
                    environment=environment,
                    rules=(
                        rules_decision.record
                        if fallback.adapter == "prism"
                        else {"status": "not-applicable", "adapter": fallback.adapter}
                    ),
                    unavailable_reason=(
                        codex_reason if fallback.adapter == "codex" else None
                    ),
                )
            )
        _reconfirm_tree_binding(repo, target, selected)
    else:
        attempts = []
    attempts.sort(key=lambda item: str(item["provider"]["id"]))
    findings = _normalize_findings(attempts)
    applied = _apply_local_dispositions(findings, supplied)
    ceiling = plan.get("localAdvisorySeverityCeiling")
    outstanding, advisory, dispositioned, accepted = _classify_findings(
        findings, ceiling
    )
    outcome = _aggregate_outcome(attempts)
    limitations = [
        f"{item['provider']['id']}:{item['status']}"
        for item in attempts
        if item["status"] in TERMINAL_FAILURES
    ]
    receipt = {
        "schemaVersion": 1,
        "receiptId": identity,
        "attemptId": attempt_id,
        "target": target,
        "plan": plan,
        "outcome": outcome,
        "attempts": attempts,
        "findings": findings,
        "disposition": {
            "outstanding": outstanding,
            "advisory": advisory,
            "dispositioned": dispositioned,
            "accepted": accepted,
            "fixPolicy": fix_policy,
            "maximumFixCommitsBeforeRemote": 1,
            "localDispositions": applied,
        },
        "remoteGate": _remote_gate(
            outcome,
            outstanding,
            local_policy,
            plan["familyGate"],
            findings_present=bool(findings),
            advisory=advisory,
            dispositioned=dispositioned,
            accepted=accepted,
            degraded=bool(limitations),
        ),
        "confidence": {"granted": outcome == "clean", "limitations": limitations},
        "createdAt": time.time(),
    }
    _atomic_json(receipt_path, receipt)
    return receipt, False


def _remote_summary(receipt: Mapping[str, Any]) -> dict[str, Any]:
    target = receipt["target"]
    plan = receipt["plan"]
    attempts = receipt["attempts"]
    findings = receipt["findings"]
    return {
        "schemaVersion": 1,
        "repository": target["repository"],
        "base": target["base"],
        "head": target["head"],
        "contentDigest": target["contentDigest"],
        "receiptId": receipt["receiptId"],
        "outcome": receipt["outcome"],
        "providers": [
            {
                "id": row["provider"]["id"],
                "costTier": row["provider"]["costTier"],
                "qualityTier": row["provider"]["qualityTier"],
                "status": row["status"],
                "durationMs": row["durationMs"],
            }
            for row in attempts
        ],
        "findingCounts": {
            "total": len(findings),
            "outstanding": receipt["disposition"]["outstanding"],
        },
        "policyId": plan["policyId"],
        "familyGate": plan["familyGate"],
        "providerCostTiers": sorted(
            {row["provider"]["costTier"] for row in attempts}
        ),
        "remoteGate": receipt["remoteGate"],
        "confidence": receipt["confidence"],
    }


def _report(receipt: Mapping[str, Any], *, reused: bool) -> dict[str, Any]:
    outcome = receipt["outcome"]
    return {
        "schemaVersion": 1,
        "command": "sd-review-local-stage",
        # ``outcome`` is the verdict envelope key (A-077); ``status`` is the
        # deprecated alias emitting the identical value for the dual-emit
        # window (removed_version 0.66.0, see DEPRECATED_PAYLOAD_KEYS).
        "outcome": outcome,
        "status": outcome,
        "run": "reused" if reused else "executed",
        "receipt": receipt,
        "remoteSummary": _remote_summary(receipt),
    }


def _invalid_report(message: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "command": "sd-review-local-stage",
        "outcome": "invalid",
        "status": "invalid",  # deprecated alias of ``outcome`` (A-077)
        "diagnostic": _bounded(message),
    }


def _cancelled_report() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "command": "sd-review-local-stage",
        "outcome": "cancelled",
        "status": "cancelled",  # deprecated alias of ``outcome`` (A-077)
        "diagnostic": "local review stage cancelled by signal",
    }


def _print_human(report: Mapping[str, Any]) -> None:
    print(f"Local review stage: {report['outcome']}")
    if report.get("diagnostic"):
        print(f"Diagnostic: {report['diagnostic']}")
        return
    receipt = report["receipt"]
    plan = receipt["plan"]
    print(
        f"Plan: {plan['policyId']} ({', '.join(row['id'] for row in plan['providers']) or 'none'})"
    )
    print(f"Execution: {report['run']}")
    print(f"Exact head: {receipt['target']['head']}")
    print(f"Remote gate: {receipt['remoteGate']['state']}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--scope", choices=sorted(SCOPES), default="branch")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--local", default="auto")
    parser.add_argument(
        "--successor",
        choices=("first", "low-risk", "high-risk", "repeated-family", "bookkeeping"),
        default="first",
    )
    parser.add_argument("--finding-family", action="append", default=[])
    parser.add_argument("--local-disposition", action="append", default=[])
    parser.add_argument("--family-evidence")
    parser.add_argument("--bookkeeping-evidence")
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--artifact-root")
    parser.add_argument(
        "--local-policy", choices=("optional", "required"), default="optional"
    )
    parser.add_argument("--fix", choices=("auto", "ask", "none"), default="auto")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--no-reuse", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report: dict[str, Any]
    try:
        if not ATTEMPT_RE.fullmatch(args.attempt_id):
            raise ReviewInputError("attempt id must be a bounded identifier")
        repo = Path(args.repo).resolve(strict=True)
        if not (repo / ".git").exists():
            raise ReviewInputError(f"not a Git repository: {repo}")
        config, providers, policy = load_config(repo)
        target = resolve_target(repo, args.scope, args.base, args.head)
        evidence = _bookkeeping_evidence_path(args.bookkeeping_evidence)
        family_evidence = (
            Path(args.family_evidence).absolute()
            if args.family_evidence
            else None
        )
        family_gate = _family_gate(family_evidence, target)
        family_values = sorted(
            set(args.finding_family) | set(family_gate["repeatedFamilies"])
        )
        successor = (
            "repeated-family"
            if family_gate["state"] == "sibling-audit-required"
            else args.successor
        )
        plan = build_plan(
            providers=providers,
            policy=policy,
            target=target,
            local=args.local,
            local_policy=args.local_policy,
            fix_policy=args.fix,
            successor=successor,
            finding_families=family_values,
            family_gate=family_gate,
            bookkeeping_evidence=evidence,
            configuration_digest=_digest(config),
        )
        if CANCELLATION_EVENT.is_set():
            report = _cancelled_report()
            code = 3
        elif family_gate["state"] == "round-extension-required":
            report = {
                "schemaVersion": 1,
                "command": "sd-review-local-stage",
                "status": "blocked",
                "diagnostic": (
                    "a repeated post-audit finding family requires an approved "
                    "review.round-extension decision before another provider request"
                ),
                "familyGate": family_gate,
            }
            code = 1
        elif args.plan_only:
            report = {
                "schemaVersion": 1,
                "command": "sd-review-local-stage",
                "status": "planned",
                "target": target,
                "plan": plan,
            }
            code = 0
        else:
            root = _artifact_root(repo, args.artifact_root)
            receipt, reused = execute(
                repo=repo,
                artifact_root=root,
                attempt_id=args.attempt_id,
                target=target,
                plan=plan,
                providers=providers,
                local_policy=args.local_policy,
                fix_policy=args.fix,
                allow_reuse=not args.no_reuse,
                dispositions=_parse_local_dispositions(args.local_disposition),
                fallbacks=cheapest_fallbacks(providers, policy, target, plan),
            )
            report = _report(receipt, reused=reused)
            code = (
                0
                if receipt["outcome"] in {"clean", "skipped"}
                else 1
                if receipt["outcome"] == "findings"
                else 3
            )
    except (OSError, ReviewInputError) as error:
        report = _invalid_report(str(error))
        code = 2
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        _print_human(report)
    return code


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_termination)
    signal.signal(signal.SIGTERM, _handle_termination)
    raise SystemExit(main())
